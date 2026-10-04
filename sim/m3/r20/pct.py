from lib import *
W=4800
def stat(Pw):
    Pw=Pw[Pw>0]; q=np.percentile(Pw,[10,50,90]); return 10*np.log10(q[2]/q[0]), 10*np.log10(q[1]/q[0])
def pcb(pid,a,b):
    x=wav(D+'sim/pcb_audio/%s.wav'%pid).mean(1); x=bp(x[int(a*48000):int(b*48000)]); P=pw(x,W)
    nz=np.percentile(pw(bp(wav(D+'sim/pcb_audio/%s.wav'%pid).mean(1)[:48000*200]),W),0.5)
    return P-0, nz
c=core(D+'sim/build/m3/sr_play/aud.raw'); c=bp(c-c.mean(0)); m=bp(wav(D+'sim/mame/out/m3_sr_play/mame.wav').mean(1))
sel=lambda P,ranges: np.concatenate([P[int(a*10):int(b*10)] for a,b in ranges])
R=[(13,37.5),(48,62)]
Pc=pw(c,W); Pm=pw(m,W)
print('core sr_play gameplay windows', len(sel(Pm,R)))
print('P90-P10, P50-P10 (dB)')
print('MAME sr_play    %.2f %.2f'%stat(sel(Pm,R)))
print('core mix sr_play %.2f %.2f'%stat(sel(Pc[:,3],R)))
for k in (1,1.25,1.5,1.75,2,2.5):
    x=Pc[:,0]+k*k*Pc[:,2]+Pc[:,1]*(2775/102)**2
    print('  model k=%.2f   %.2f %.2f'%((k,)+stat(sel(x,R))))
for pid,a,b in (('HrMhhSO97-A',15,855),('amenau-jqpo',8,3410)):
    x=bp(wav(D+'sim/pcb_audio/%s.wav'%pid).mean(1)); P=pw(x,W)
    print(pid,'noise floor (min 1%%) %.1f dB, P10 %.1f dB'%(10*np.log10(np.percentile(P,1)),10*np.log10(np.percentile(P[int(a*10):int(b*10)],10))), ' %.2f %.2f'%stat(P[int(a*10):int(b*10)]))
