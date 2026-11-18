"""Rebuild only the AI quota chime. Other reminder recordings remain unchanged."""
from array import array
from math import cos, exp, pi, sin
from pathlib import Path
import sys
import wave


RATE = 24000
# Quiet, consonant notes without a sharp attack, pitch sweep or noise layer.
DURATION = .60
NOTES = ((0, 587.330, .85), (.14, 523.251, .85))


def tone(t, frequency):
    if t <= 0:
        return 0.0
    attack = sin(min(1, t / .024) * pi / 2) ** 2
    envelope = attack * exp(-t / .155)
    # A warm sine body with restrained glass-like overtones. Tiny fixed detuning
    # gives the tail space; no random noise, tremolo or bird-like pitch bend.
    return envelope * (sin(2*pi*frequency*t)
                       + .065*sin(2*pi*frequency*2*t)*exp(-t/.11)
                       + .018*sin(2*pi*(frequency*3+.7)*t)*exp(-t/.08)
                       + .035*sin(2*pi*(frequency+1.2)*t))


def samples(duration, notes):
    values = []
    for index in range(round(duration*RATE)):
        t = index/RATE
        value = sum(level*(tone(t-onset, pitch)
                    + .16*tone(t-onset-.052, pitch)
                    + .07*tone(t-onset-.113, pitch))
                    for onset, pitch, level in notes)
        tail = .5 - .5*cos(pi*min(1, max(0, (duration-t-1/RATE)/.085)))
        values.append(.155*value*tail)
    assert max(map(abs, values)) < .23
    return values


def generate(destination):
    destination.mkdir(parents=True, exist_ok=True)
    pcm = array('h', (round(value*32767) for value in samples(DURATION, NOTES)))
    if sys.byteorder != 'little':
        pcm.byteswap()
    with wave.open(str(destination/'quota.wav'), 'wb') as sound:
        sound.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        sound.writeframes(pcm.tobytes())


if __name__ == '__main__':
    generate(Path(__file__).resolve().parents[1]/'assets/reminder-sounds')
