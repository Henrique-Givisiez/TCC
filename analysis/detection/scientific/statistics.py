"""Run/block-level CIs. Never treats windows or requests as independent trials."""
from math import sqrt,log
import warnings
import numpy as np
from scipy.stats import norm,beta,bootstrap
from ..inputs import ContractError
from .protocol import SPEC


def exact_ci(k,n,level=.95):
    if type(k) is not int or type(n) is not int or not 0<=k<=n:raise ContractError('Invalid binomial counts')
    if n==0:return None
    tail=(1-level)/2
    return [0.0 if k==0 else float(beta.ppf(tail,k,n-k+1)),
            1.0 if k==n else float(beta.ppf(1-tail,k+1,n-k))]


def proportion_ci(k,n):
    if n==0:return dict(n=0,estimate=None,interval=None,method='undefined')
    if k in (0,n):interval=exact_ci(k,n);method='exact_binomial'
    else:
        if not 0<k<n:raise ContractError('Invalid proportions')
        z=float(norm.ppf(.975));p=k/n;den=1+z*z/n
        center=(p+z*z/(2*n))/den;half=z*sqrt(p*(1-p)/n+z*z/(4*n*n))/den
        interval=[center-half,center+half];method='Wilson'
    return dict(n=n,successes=k,estimate=k/n,interval=interval,method=method,level=.95)


def mean_ci(values,bounds=(0.,1.)):
    values=np.asarray(values,dtype=float);n=len(values);lo,hi=bounds
    if n==0:return dict(n=0,estimate=None,interval=None,method='undefined')
    if not np.all(np.isfinite(values)) or not np.all((values>=lo)&(values<=hi)):raise ContractError('CI values outside declared bounds')
    mean=float(np.mean(values));interval=None
    if n>=2 and np.ptp(values)>0:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            result=bootstrap((values,),np.mean,n_resamples=10000,method='BCa',confidence_level=.95,
                random_state=np.random.RandomState(SPEC['ci']['rng_seed']))
        interval=[float(result.confidence_interval.low),float(result.confidence_interval.high)]
    method='BCa_block_mean'
    if interval is None or not np.all(np.isfinite(interval)):
        half=(hi-lo)*sqrt(log(40)/(2*n));interval=[mean-half,mean+half];method='Hoeffding_degenerate'
    return dict(n=n,estimate=mean,interval=[max(lo,interval[0]),min(hi,interval[1])],method=method,
        unit='whole_block',level=.95,replicates=10000,rng_seed=SPEC['ci']['rng_seed'])


def paired_mean_ci(left,right,bounds=(-1.,1.)):
    if len(left)!=len(right):raise ContractError('Paired values not aligned')
    # Difference BEFORE resampling: every draw keeps the original pair.
    return mean_ci([a-b for a,b in zip(left,right)],bounds)


def paired_detection_ci(left,right):
    if len(left)!=len(right) or any(type(x) is not bool for x in (*left,*right)):
        raise ContractError('Paired event decisions must be aligned booleans')
    n=len(left)
    if not n:return dict(n=0,estimate=None,interval=None,method='undefined')
    n10=sum(a and not b for a,b in zip(left,right));n01=sum(b and not a for a,b in zip(left,right))
    a,b=exact_ci(n10,n,.975),exact_ci(n01,n,.975)
    return dict(n=n,n10=n10,n01=n01,estimate=(n10-n01)/n,interval=[a[0]-b[1],a[1]-b[0]],
        method='paired_discordant_exact_Bonferroni',level=.95)


def delay_summary(values):
    a=[float(x) for x in values if x is not None];n=len(a)
    return dict(detected=n,mean_seconds=float(np.mean(a)) if a else None,
        median_seconds=float(np.median(a)) if a else None,
        interval=mean_ci(a,(0.,300.))['interval'] if n>=8 else None,
        reason=None if n>=8 else 'conditional_support_below_8',unit='detected_runs_only')
