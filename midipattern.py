import time
import copy
from abc import abstractmethod

# Midi file parser
import midi

# Midi Playback
import pygame
import pygame.midi
from pygame.mixer import music


def copy_event(e):
    '''
    Deep copy of midi.Event and related
    This is a hack; it would be better to have a copy()
    
    Test
    ----
    >>> n = midi.NoteOnEvent()
    >>> m = copy_event(n)
    >>> m.set_velocity(23)
    >>> m.get_velocity() == n.get_velocity()
    '''
    if isinstance(e, midi.Event):
        new_e = e.copy()
        new_e.data = list(new_e.data)
        return new_e
    elif isinstance(e, midi.AbstractEvent):
        new_e = e.__class__(tick=e.tick, data=list(e.data))
        return new_e
    else:
        raise ValueError('could not clone {}'.format(e))
        

class MidiPattern(midi.Pattern):
    '''
    Change MIDI_DEVICE according to settings
    '''
    MIDI_DEVICE = 0
    
    # Types of event
    #
    # Important events are:
    # NoteOnEvent
    # NoteOffEventevents
    # ControlChangeEvent
    # ProgramChangeEvent
    # EndOfTrackEvent
    # SetTempoEvent
    # KeySignatureEvent
    #
    # Warning: NoteOnEvent with velocity 0 === NoteOffEvent
    
    def __init__(self, pattern):
        '''
        Build from midi.Pattern object
        '''
        if not isinstance(pattern, midi.Pattern):
            raise ValueError

        # clone or build
        copy_tracks = [midi.Track([copy_event(e) for e in track]) 
                       for track in pattern]
        midi.Pattern.__init__(self, tracks=copy_tracks, 
                              resolution=pattern.resolution, 
                              format=pattern.format, 
                              tick_relative=pattern.tick_relative)
        
        # copy attributes if needed
        if 'attributes' in pattern.__dict__:
            self.attributes = copy.deepcopy(pattern.attributes)
       
    def zero(self):
        '''
        Zero the tracks
        '''
        self[:] = []
        return self
        
    def init_attributes(self):
        '''
        Init attributes associated to events
        '''
        # add attributes
        self.attributes = [[{} for e in track] for track in self]
        
    def stamp_time(self, label, bpm=None):
        '''
        Add timestamp to each note's attribute,
        accounting for changes in tempo
        '''
        if not 'attributes' in self.__dict__:
            self.init_attributes()
        # Default Bpm is 120
        # If bpm is given, override all bpm changes
        fixed_bpm = (bpm is not None)
        bpm = 120. if bpm is None else float(bpm)
        for track, track_attributes in zip(self, self.attributes):
            total_time = 0.
            for e, e_attr in zip(track, track_attributes):
                dt = 60. / bpm / self.resolution * e.tick
                total_time += dt
                e_attr[label] = total_time

                if (isinstance(e, midi.SetTempoEvent) and not fixed_bpm):
                    bpm = e.get_bpm()
                    
    def sort_all(self):
        '''
        Jointly sort events and attributes, in-place
        '''
        was_relative = self.tick_relative
        self.make_ticks_abs()
        for track, track_attributes in zip(self, self.attributes):
            new_track, new_track_attr = zip(*sorted(zip(track, track_attributes), key=lambda (a, b): a.tick))
            track[:] = midi.Track(new_track, tick_relative=False)
            track_attributes[:] = new_track_attr
        if was_relative:
            self.make_ticks_rel()
                    
    def play(self, bpm=None, instrument=None, verbose=False):
        '''
        Play pattern if in midi-0 format
        
        Parameters
        ----------
        bpm : Number, optional
            beats per minute (quarter notes)
            if given, tempo will be forced to bpm
        instrument : int, optional
            instrument in GM-1 table
            if not given, use given instruments
        '''
        '''
        if len(self) != 1 or self.format != 0:
            raise Exception('need midi-1')
        '''
        midi_player = pygame.midi.Output(self.MIDI_DEVICE)
        if instrument is not None:
            for ch in xrange(16):
                midi_player.set_instrument(instrument, ch)
        try:
            simple = self.simplified(bpm)
            # Default Bpm is 120
            # If bpm is given, override all bpm changes
            fixed_bpm = (bpm is not None)
            bpm = 120. if bpm is None else float(bpm)
            total_time = 0.
            for note_idx, note in enumerate(simple[0]):
                tick = note.tick
                dt = 60. / bpm / self.resolution * tick
                total_time += dt
                time.sleep(dt)
                if isinstance(note, midi.NoteEvent):
                    pitch = note.get_pitch()
                    velocity = note.get_velocity()
                    midi_player.note_on(pitch, velocity)
                elif (isinstance(note, midi.SetTempoEvent) and
                    not fixed_bpm):
                    bpm = note.get_bpm()
                    if verbose: print 'bpm change:', bpm
                elif (isinstance(note, midi.ProgramChangeEvent) and
                      instrument is None):
                    if verbose: print note
                    midi_player.set_instrument(note.value, note.channel)
        except KeyboardInterrupt:
            print 'Was playing note', note_idx, 'time', total_time
        finally:
            del midi_player
            
    def fix_bpm(self, bpm):
        if not self.tick_relative:
            raise Exception('convert to relative ticks first')
        tempo_event = midi.SetTempoEvent()
        tempo_event.set_bpm(bpm)
        # filter out tempo events
        for track in self:
            track[:] = midi.Track([e for e in track
                  if not isinstance(e, midi.SetTempoEvent)], 
                                  tick_relative=False)
        # add single tempo
        self[0].insert(0, tempo_event)
            
    def simplified(self, bpm=None):
        '''
        Simplify midi pattern by keeping only important events.
        Merge all tracks to one (midi-0 convention)

        Parameters
        ----------
        bpm : Number, optional
            beats per minute (quarter notes)
            if given, tempo will be forced to bpm [TODO],
            and all tempo events will be dropped

        Events Kept:
            midi.NoteEvent
            #midi.EndOfTrackEvent (only the last one is kept)
            midi.SetTempoEvent (if bpm is not given)
            midi.ProgramChangeEvent
            
        Returns
        -------
        simple : MidiEvent
            simplified MidiEvent
        '''
        # Change ticks to absolute and sort
        tmp = MidiPattern(self)
        tmp.make_ticks_abs()
        events = []
        for track in tmp:
            for e in track:
                events.append(e)
        events.sort()

        # Filter
        new_track = midi.Track([e for e in events
                  if isinstance(e, midi.NoteEvent) or 
                  isinstance(e, midi.ProgramChangeEvent) or
                  (isinstance(e, midi.SetTempoEvent) and
                   not bpm)], tick_relative=False)

        # Keep last end of track event
        end_of_track = max(e for e in events 
                           if isinstance(e, midi.EndOfTrackEvent))
        new_track.append(end_of_track)

        # To pattern, change to relative
        new_pattern = MidiPattern(self).zero()
        new_pattern.append(new_track)
        new_pattern.make_ticks_rel()

        # Fix bpm if needed
        if bpm:
            new_pattern.fix_bpm(bpm)
        
        return new_pattern
    
    
#if __name__ == '__main__':
pygame.init()
pygame.midi.init()
# RUN timidity -iA !!
for id in xrange(pygame.midi.get_count()):
    print 'device', id, pygame.midi.get_device_info(id)