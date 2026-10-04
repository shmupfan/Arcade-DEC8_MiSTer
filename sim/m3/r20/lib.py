import numpy as np, wave
from scipy.signal import butter, sosfiltfilt
import os
D=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))+'/'
def wav(p):
    w=wave.open(p); x=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(np.float64).reshape(-1,w.getnchannels()); return x
def core(p):
    c=np.fromfile(p,dtype='<i2').astype(np.float64).reshape(-1,4)
    c[:,1]=np.fromfile(p,dtype='<u2').astype(np.float64).reshape(-1,4)[:,1]
    return c
def bp(x,band=3500.0,lo=20.0):
    sos=butter(6,[lo,band],btype='bandpass',fs=48000,output='sos'); return sosfiltfilt(sos,x,axis=0)
def pw(x,win=960):
    k=len(x)//win; return (x[:k*win].reshape(k,win,*x.shape[1:])**2).mean(axis=1)
