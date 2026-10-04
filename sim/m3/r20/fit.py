"""PCB power envelope as NNLS of core per-chip power envelopes.
usage: fit.py PCBID COREDIR MAMEWAV [t0 t1 (ref seconds)] [--bands]"""
import sys,os; from lib import *
from scipy.optimize import nnls
pid,cdir,mw=sys.argv[1:4]
t0=float(sys.argv[4]) if len(sys.argv)>4 else 0.5
t1=float(sys.argv[5]) if len(sys.argv)>5 else 1e9
bands=[(20,3500)] + ([(100,250),(250,500),(500,1000),(1000,2000),(2000,3500)] if '--bands' in sys.argv else [])
p_raw=wav(D+'sim/pcb_audio/%s.wav'%pid).mean(1)
m_raw=wav(D+mw).mean(1)
c_raw=core(D+cdir+'/aud.raw'); c_raw=c_raw-c_raw.mean(0)
n=min(len(m_raw),len(c_raw)); m_raw,c_raw=m_raw[:n],c_raw[:n]
# 1) PCB -> ref (MAME) lag model: 1 ms log-envelope xcorr per 5 s ref segment, robust line
def env(x,w): k=len(x)//w; return np.sqrt((x[:k*w].reshape(k,w)**2).mean(1))
pb,mb=bp(p_raw),bp(m_raw)
ep,em=env(pb,48),env(mb,48)
LO,HI=[int(v) for v in os.environ.get('LAGWIN','1500,1950').split(',')]
pts=[]
for s in range(0,len(em)-5000,5000):
    b=em[s:s+5000]
    if b.std()<1: continue
    best=None
    for L in range(LO,HI):
        j=s+L
        if j<0 or j+5000>len(ep): continue
        r=np.corrcoef(np.log(b+30),np.log(ep[j:j+5000]+30))[0,1]
        if best is None or r>best[1]: best=(L,r)
    if best and best[1]>0.15: pts.append((s+2500,best[0],best[1]))
pts=np.array(pts)
keep=np.ones(len(pts),bool)
for it in range(3):
    A=np.polyfit(pts[keep,0],pts[keep,1],1); res=pts[:,1]-np.polyval(A,pts[:,0]); keep=np.abs(res)<max(8,3*np.median(np.abs(res[keep])))
print('lag model: pcb_t = ref_t*(1%+.5f) %+.3f s ; segs %d/%d kept, resid max kept %.1f ms'%(A[0],A[1]/1000,keep.sum(),len(pts),np.abs(res[keep]).max()))
W=int(float(os.environ.get('WIN','20'))*48)
k=n//W
tref=np.arange(k)*W
tp=np.round(tref*(1+A[0])+A[1]*48).astype(int)
ok=(tp>=0)&(tp+W<=len(p_raw))&(tref/48000>=t0)&(tref/48000<t1)
def wpow(x,starts): return np.array([(x[s:s+W]**2).mean() for s in starts])
out={}
for lo,hi in bands:
    pf,mf=bp(p_raw,hi,lo),bp(m_raw,hi,lo); cf=bp(c_raw,hi,lo)
    P=pw(cf[:k*W],W)  # k x 4
    PP=np.zeros(k); PP[ok]=wpow(pf,tp[ok])
    PM=pw(mf[:k*W],W)
    noise=np.percentile(PP[ok],2)
    sel=ok&(PM>1e3)
    X=P[sel][:,:3]
    def fit(y,X):
        g,_=nnls(X,y); return g
    def ratios(g): return np.sqrt(g[2]/g[0]) if g[0]>0 else np.inf, np.sqrt(g[1]/g[0]) if g[0]>0 else np.inf
    # block bootstrap over 2 s blocks
    idx=np.where(sel)[0]; blk=idx//(2*48000//W); ub=np.unique(blk)
    rng=np.random.default_rng(1)
    def boot(y):
        rs=[]
        for _ in range(400):
            bs=rng.choice(ub,len(ub)); ii=np.concatenate([np.where(blk==b)[0] for b in bs])
            g=fit(y[ii],X[ii]); rs.append(ratios(g))
        rs=np.array(rs); return np.percentile(rs,[5,50,95],axis=0)
    for name,y in (('PCB',PP[sel]-noise),('MAME',PM[sel]),('coremix',P[sel][:,3])):
        g=fit(y,X); r=ratios(g); b=boot(y)
        pred=X@g; r2=1-((y-pred)**2).sum()/((y-y.mean())**2).sum()
        # log-envelope correlation too
        q=(y>0)&(pred>0); sl=np.polyfit(np.log10(pred[q]),np.log10(y[q]),1)[0]
        print('   log-log slope of %s window power on its fitted prediction: %.3f (1 = linear, <1 = compression)'%(name,sl))
        print('%5d-%4d Hz %-7s OPL:FM %.2f [%.2f-%.2f]  SSG:FM %.2f [%.2f-%.2f]  R2 %.2f  n=%d  => gains FM102 OPL %.0f SSG %.0f'%(lo,hi,name,r[0],b[0][0],b[2][0],r[1],b[0][1],b[2][1],r2,sel.sum(),102*r[0],102*r[1]))
    out[(lo,hi)]=(PP,PM,P,sel)
    if '--segs' in sys.argv and (lo,hi)==(20,3500):
        segw=int(10*48000/W); seg=np.arange(k)//segw
        for sg in np.unique(seg[sel]):
            q=sel&(seg==sg)
            if q.sum()<100: continue
            line='  seg %5.1f-%5.1f s n=%3d'%(sg*10*W*segw/48000/10*1.0*1,(sg+1)*segw*W/48000,q.sum())
            for name,y in (('PCB',PP[q]-noise),('MAME',PM[q]),('coremix',P[q][:,3])):
                g,_=nnls(P[q][:,:3],y); line+='  %s OPL:FM %.2f'%(name,np.sqrt(g[2]/g[0]) if g[0]>0 else np.inf)
            print(line)

