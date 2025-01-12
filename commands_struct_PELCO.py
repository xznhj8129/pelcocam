class libpelco_structs():

    _frame = {
        'synch_byte':'\xFF',
        'address':   '\x00',
        'command1':  '\x00',
        'command2':  '\x00',
        'data1':     '\x00',
        'data2':     '\x00',
        'checksum':  '\x00'
    }

    _function_code = {
        'DOWN':            '\x10',
        'UP':              '\x08',    
        'LEFT':            '\x04',
        'RIGHT':           '\x02',
        'UP-RIGHT':        '\x0A',
        'DOWN-RIGHT':      '\x12',
        'UP-LEFT':         '\x0C',
        'DOWN-LEFT':       '\x14',
        'STOP':            '\x00',
        'ZOOM-IN':         '\x20',
        'ZOOM-OUT':        '\x40',
        'FOCUS-FAR':       '\x80',
        'FOCUS-NEAR':      '\x81',
        'SET-PRESET':      '\x03',
        'CLEAR-PRESET':    '\x05',
        'CALL-PRESET':     '\x07',
        'QUERY-PAN':       '\x51',
        'QUERY-TILT':      '\x53',
        'QUERY-ZOOM':      '\x55'
    }

# END

