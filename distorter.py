'''
TODO
add/drop notes
replace notes

WARNING
if elements are inserted or deleted,
need to rebuild attributes!!
'''

from abc import abstractmethod
import numpy as np
import midi
from midipattern import MidiPattern


class Distorter(object):
    '''
    Distort a *simplified* pattern.
    
    Ways of distorting a pattern include changing its tempo,
    introducing randomness on the timing of individual notes (ticks),
    or changing the instruments (channel).
    
    No need to preserve measures.
    '''
    def distort(self, pattern, keep_stamps=False):
        '''
        Distort a pattern.
        
        Decorates _distort:
        - create new_pattern from pattern
        - add attributes and timestamps to new_pattern
        - call _distort()
        - add new timestamps to new_pattern
        
        
        Parameters
        ----------
        pattern : MidiPattern
            *simplified* pattern
        keep_stamps : bool
            if True, keep original time stamps 't0'
            typically, when applying a chaing of distortions,
            keep stamps except for the first distortion
            
        Returns
        -------
        new_pattern : MidiPattern
            new distorted pattern
        align : list
            alignment of new_pattern to input pattern
        '''
        new_pattern = MidiPattern(pattern)
        if not keep_stamps:
            new_pattern.init_attributes()
            new_pattern.stamp_time('t0')
        new_pattern = self._distort(pattern, new_pattern)
        new_pattern.sort_all()
        new_pattern.stamp_time('t')
        return new_pattern
    
    @abstractmethod
    def _distort(self, pattern, new_pattern):
        '''
        Actual implementation. Modifies new_pattern in place.
        
        Parameters
        ----------
        pattern : MidiPattern
            input pattern
        new_pattern : MidiPattern
            pattern to return
        '''
        pass
    
    @abstractmethod
    def __repr__(self):
        pass
    
    def randomize(self, params):
        '''
        Sample parameters of distorter.
        
        Parameters
        ----------
        params : dict
            hyperparameters defining distribution on parameters
        '''
        pass
    
    def __repr__(self):
        name = self.__class__.__name__
        params = ['{}={}'.format(k,v) for k,v in self.__dict__.items()]
        return '<{}({})>\n'.format(name, ','.join(params))
    

class VelocityNoiseDistorter(Distorter):
    '''
    Add gaussian noise on individual velocities
    '''
    def __init__(self, sigma=10.):
        '''
        Parameters            
        
        ----------
        sigma : float
            standard deviation of gaussian noise
        '''
        self.sigma = sigma
        
    def __repr__(self):
        return 'VelocityNoiseDistorter(sigma={:.2f})'.format(self.sigma) 
            
    def randomize(self, params=None):
        '''
        Parameters
        ----------
        params : dict
            min_sigma, max_sigma : float
                where self.sigma ~ U(min_sigma, max_sigma)
        '''
        p = {'min_sigma': 0., 'max_sigma': 20.}
        if params:
            p.update(params)
        self.sigma = np.random.uniform(
            p['min_sigma'], p['max_sigma'])
        
    def _distort(self, pattern, new_pattern):
        for track in new_pattern:
            for e in track:
                if (isinstance(e, midi.NoteOnEvent) and
                        e.get_velocity() > 0):
                    tmp_velocity = e.get_velocity() + self.sigma*np.random.normal() 
                    e.set_velocity(np.clip(int(tmp_velocity), 1, 127))
        return new_pattern

    
class VelocityWalkDistorter(Distorter):
    '''
    Generate bounded random walk,
    and multiply velocities by it.
    '''
    def __init__(self, sigma=10., min=0.5, max=2.):
        '''
        Parameters
        ----------
        sigma : float
            standard deviation of derivative of random walk
            per quarter note
        min : float
            minimum multiple of original velocity
        max : float
            maximum multiple of original velocity
        '''
        self.sigma = sigma
        self.min = min
        self.max = max
        
    def __repr__(self):
        return 'VelocityWalkDistorter(sigma={:.2f}, min={:.2f}, max={:.2f})'.format(self.sigma, self.min, self.max) 
    
    def randomize(self, params=None):
        '''
        Parameters
        ----------
        params : dict
            min_sigma, max_sigma : float
                where self.sigma ~ U(min_sigma, max_sigma)
            min, max : float
                where self.min, self.max ~ U(min, max)
                and min < max
        '''
        p = {'min_sigma': 0., 'max_sigma': 20.,
             'min': 0.3, 'max': 1.5}
        if params:
            p.update(params)
        self.sigma = np.random.uniform(p['min_sigma'], p['max_sigma'])
        a, b = np.random.uniform(p['min'], p['max'], size=2)
        self.min = min(a, b)
        self.max = max(a, b)
        
    def _distort(self, pattern, new_pattern):
        sigma_per_tick = self.sigma / np.sqrt(pattern.resolution)
        multiple = 1.  # original value
        for track in new_pattern:
            for e in track:
                tmp_multiple = (multiple + sigma_per_tick 
                                * np.random.normal()
                                * np.sqrt(float(e.tick)))
                multiple = np.clip(tmp_multiple, self.min, self.max)
                #print multiple
                if (isinstance(e, midi.NoteOnEvent) and
                        e.get_velocity() > 0):
                    tmp_velocity = e.get_velocity() * multiple
                    e.set_velocity(np.clip(int(tmp_velocity), 1, 127))
        return new_pattern
    
    
class ProgramDistorter(Distorter):
    '''
    Change Instrument
    '''
    def __init__(self, ticks=0):
        '''
        Parameters
        ----------
        ticks : int
            change instrument every ticks
        '''
        self.ticks = ticks
        
    def __repr__(self):
        return 'ProgramDistorter(ticks={:.2f})'.format(self.ticks)
    
    def randomize(self, params=None):
        '''
        For now, just sample an instrument from the list at random.
        
        Parameters
        ----------
        params : dict
            instruments : list of int
                list of instruments to sample from
        
        [TODO]
        Parameters
        ----------
        params : dict
            lambda : float
                define distribution on number of instruments self.ni
                where self.ni ~ Exp(lambda)
                i.e., P(self.ni)
            min, max : float
                where self.min, self.max ~ U(min, max)
                and min < max
        '''
        p = {'instruments': [0, 1, 2, 3]}
        if params:
            p.update(params)
        self.instrument = np.random.choice(p['instruments'])
        
    def _distort(self, pattern, new_pattern):
        new_pattern.zero()
        new_events = [midi.ProgramChangeEvent(
                channel=ch,
                value=self.instrument) for ch in xrange(16)]
        for idx, e in enumerate(pattern[0]):
            if not isinstance(e, midi.ProgramChangeEvent):
                new_events.append(e)
                '''
                if idx % self.ticks == 0:
                    instrument = np.random.randint(4)
                    new_events += [midi.ProgramChangeEvent(
                        channel=ch,
                        value=instrument) for ch in xrange(16)]
                '''
        new_pattern.append(midi.Track(new_events))
        # Rebuild attributes and stamps
        new_pattern.init_attributes()
        new_pattern.stamp_time('t0')
        return new_pattern
    
    
class TempoDistorter(Distorter):
    '''
    Change tempo by offsetting ticks.
    
    This ignores SetTempoEvent and does not introduce additional ones.
    Instead it offsets the ticks.
    '''
    def __init__(self, sigma=0.5, min=0.5, max=2.):
        '''
        Parameters
        ----------
        sigma : float
            standard deviation of derivative of random walk
            per quarter note
        min : float
            minimum multiple of original tempo
        max : float
            maximum multiple of original tempo
        '''
        self.sigma = sigma
        self.min = min
        self.max = max
        
    def __repr__(self):
        return 'TempoDistorter(sigma={:.2f}, min={:.2f}, max={:.2f})'.format(self.sigma, self.min, self.max) 
    
    def randomize(self, params=None):
        '''
        Parameters
        ----------
        params : dict
            min_sigma, max_sigma : float
                where self.sigma ~ U(min_sigma, max_sigma)
            min, max : float
                where self.min, self.max ~ U(min, max)
                and min < max
        '''
        p = {'min_sigma': 0., 'max_sigma': 1.,
             'min': 0.6, 'max': 1.5}
        if params:
            p.update(params)
        self.sigma = np.random.uniform(p['min_sigma'], p['max_sigma'])
        a, b = np.random.uniform(p['min'], p['max'], size=2)
        self.min = min(a, b)
        self.max = max(a, b)
        
    def _distort(self, pattern, new_pattern):
        sigma_per_tick = self.sigma / np.sqrt(pattern.resolution)
        multiple = 1.  # original value
        for track in new_pattern:
            for e in track:
                tmp_multiple = (multiple + sigma_per_tick 
                                * np.random.normal()
                                * np.sqrt(float(e.tick)))
                multiple = np.clip(tmp_multiple, self.min, self.max)
                #print 'multiple {} bpm {}'.format(
                    #multiple, 120./multiple)
                tmp_tick = e.tick * multiple
                e.tick = np.clip(int(tmp_tick), 1, 127)
        return new_pattern
    
    

class TimeNoiseDistorter(Distorter):
    '''
    Add gaussian noise on individual note event ticks
    TODO: make sigma relative to note duration,
          change note duration
    
    TODO: Special care must be taken to preserve NoteOn/NoteOff precedence.
    '''
    def __init__(self, sigma=0.1):
        '''
        Parameters
        ----------
        sigma : float
            standard deviation of offset on tick in quarter notes
        '''
        self.sigma = sigma
        
    def __repr__(self):
        return 'TimeNoiseDistorter(sigma={:.2f})'.format(self.sigma)
        
    def randomize(self, params=None):
        '''
        Parameters
        ----------
        params : dict
            min_sigma, max_sigma : float
                where self.sigma ~ U(min_sigma, max_sigma)
        '''
        p = {'min_sigma': 0., 'max_sigma': 0.1}
        if params:
            p.update(params)
        self.sigma = np.random.uniform(
            p['min_sigma'], p['max_sigma'])
        
    def _distort(self, pattern, new_pattern):
        new_pattern.make_ticks_abs()
        for track, track_attributes in zip(new_pattern, new_pattern.attributes):
            for e in track:
                if (isinstance(e, midi.NoteOnEvent) and
                        e.get_velocity() > 0):
                    tmp_tick = self.sigma*np.random.normal()*pattern.resolution
                    e.tick = max(int(e.tick + tmp_tick), 1)
            # Fix end of track event - make it the last
            end_of_track_tick = max(e.tick for e in track)
            for e in track:
                if isinstance(e, midi.EndOfTrackEvent):
                    e.tick = end_of_track_tick
        new_pattern.make_ticks_rel()
        return new_pattern


def random_distort(pattern, distorters=None):
    '''
    Distort a simple pattern by applying a chain
    for distortions on it.
    
    Parameters
    ----------
    pattern : MidiPattern
        pattern to distort
    distorters : list of Distorter
        distorters to apply
    '''
    if not distorters:
        distorters = [TempoDistorter(), TimeNoiseDistorter()]
        for distorter in distorters:
            distorter.randomize()
    current = pattern
    for i, distorter in enumerate(distorters):
        keep_stamps = i > 0
        current = distorter.distort(current, keep_stamps)
    return current

