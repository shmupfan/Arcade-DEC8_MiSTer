"""Class-level cross-check: level of FM-dominated (effects) windows minus OPL-dominated (music) windows.
usage: xcheck.py PCBID COREDIR MAMEWAV t0 t1 slope offset_s"""
import sys; from lib import *
pid,cdir,mw=sys.argv[1:4]; t0,t1,A0,A1=map(float,sys.argv[4:8])
W=int(48*float(sys.argv[8])) if len(sys.argv)>8 else 4800   # 100 ms
p=bp(wav(D+'sim/pcb_audio/%s.wav'%pid).mean(1)); m=bp(wav(D+mw).mean(1))
c=core(D+cdir+'/aud.raw'); c=bp(c-c.mean(0)); n=min(len(c),len(m))
k=n//W; tr=np.arange(k)*W; tp=np.round(tr*(1+A0)+A1*48000).astype(int)
ok=(tr>=t0*48000)&(tr<t1*48000)&(tp+W<len(p))
P=pw(c[:k*W],W); PM=pw(m[:k*W],W); PP=np.array([(p[s:s+W]**2).mean() if o else 0 for s,o in zip(tp,ok)])
noise=np.percentile(PP[ok],1); 
fm,ssg,opl=P[:,0],P[:,1]*(2775/102)**2,P[:,2]   # SSG in FM-equivalent units at the core's gains
act=ok&(PM>1e4)
fmd=act&(fm>4*opl)&(ssg<0.1*fm); opd=act&(opl>4*fm)&(ssg<0.1*opl); ssd=act&(ssg>4*(fm+opl))
L=lambda x,s: 10*np.log10(x[s].mean())
print('windows %d ms: FM-dominated %d, OPL-dominated %d, SSG-dominated %d'%(W/48,fmd.sum(),opd.sum(),ssd.sum()))
for name,x in (('PCB',PP-noise),('MAME',PM),('coremix',P[:,3])):
    print('%-8s FMdom-OPLdom %+.2f dB   SSGdom-OPLdom %+.2f dB'%(name,L(x,fmd)-L(x,opd),L(x,ssd)-L(x,opd) if ssd.sum() else np.nan))
print('model mix FM*1 + OPL*k + SSG*s (core components):')
for kk in (0.8,1.0,1.25,1.5,1.75,2.0,2.5):
    x=fm+kk**2*opl+ssg
    print('  k=%.2f  FMdom-OPLdom %+.2f dB   SSGdom-OPLdom %+.2f dB'%(kk,L(x,fmd)-L(x,opd),L(x,ssd)-L(x,opd) if ssd.sum() else np.nan))
