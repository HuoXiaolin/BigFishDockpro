"""Generate the short two-note weather cue from the existing chime envelope."""
from array import array
from pathlib import Path
import sys
import wave

from generate_quota_sound import RATE, samples


def generate(destination):
    notes = ((0, 523.251, .68), (.16, 659.255, .62))
    pcm = array('h', (round(value * 32767) for value in samples(.64, notes)))
    if sys.byteorder != 'little':
        pcm.byteswap()
    with wave.open(str(destination), 'wb') as sound:
        sound.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        sound.writeframes(pcm.tobytes())


if __name__ == '__main__':
    generate(Path(__file__).resolve().parents[1] / 'assets/reminder-sounds/weather.wav')
