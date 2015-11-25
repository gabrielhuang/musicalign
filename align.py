def align_frame_to_frame(pattern, stride):
    '''
    Parameters
    ----------
    pattern : MidiPattern
        pattern with alignment attributes
        't0' for reference time
        't' for candidate time (times to align)
    stride : float
        stride of window in seconds
        
    Returns
    -------
    align : list of int
        alignment of each candidate window to index of target window
        
    TODO
    ----
    Smooth using kernel instead of binning candidate + averaging target
    reference by chord/duration of nth note
    interpolate empty reference measures    
        
    Currently, move a non-overlapping window over the pattern.
    Candidate window events have their time averaged.
    It is then assigned to the closest window.
    '''
    # Collect info for each candidate window
    windows = {}
    for track_attributes in pattern.attributes:
        for e_attr in track_attributes:
            ref_idx = int(e_attr['t'] / stride)
            windows.setdefault(ref_idx, [])
            windows[ref_idx].append(e_attr['t0'])
    # Average
    avg = {}
    for cand_idx, w in windows.items():
        avg[cand_idx] = int(sum(t for t in w) / float(len(w)))
    # Fill holes
    align = []
    last = 0.
    for cand_idx, ref_idx in sorted(avg.items()):
        # fill holes with linear interpolation
        repl = np.linspace(float(last), float(ref_idx), num=(cand_idx - len(align) + 2))[1:]
        last = ref_idx
        #repl = [ref_idx] * (cand_idx - len(align) + 1)
        align += list(repl.astype(int))
    return align
        
    
def write_align(fname, align, stride):
    '''
    Write alignment to file
    '''
    with open(fname, 'w') as f:
        f.write('{}\n'.format(stride))
        f.write('\n'.join(map(str, align)))
        
        
def read_align(fname):
    '''
    Read alignment from file\
    
    Returns
    -------
    align : list of float
        alignments in seconds for each candidate window
    stride : float
        duration of window
    '''
    with open(fname, 'r') as f:
        numbers = [float(l.strip()) for l in f]
        return numbers[1:], numbers[0]