"""Inspectable finite-wave DES. All unobserved initial values are scenario assumptions.

SimPy schedules windup, commit, impact, death, retarget and resource events.
Movement is piecewise linear with <=0.1 s replanning; this is NOT the LoL engine.
The search layer evaluates a restricted set of feedback policies, not arbitrary clicks.
"""
from __future__ import annotations
from pathlib import Path
import sys, math, json, csv, hashlib
from dataclasses import dataclass
import numpy as np

BASE=Path(__file__).parent
sys.path.insert(0,str(BASE/'vendor'))
import simpy
CFG=json.loads((BASE/'initial_state.json').read_text(encoding='utf-8'))

@dataclass
class Unit:
    id:str; side:str; kind:str; x:float; y:float; hp:float; maxhp:float
    ad:float=0.; period:float=1.; wind:float=.25; reach:float=100.; speed:float=325.
    missile:float=0.; beta:float=0.; gold:float=0.; xp:float=0.
    target:str|None=None; phase:str='walking'; ready:float=0.; armor:float=0.; mr:float=0.
    hp_gross:float=0.; hp_healed:float=0.; mana:float=0.; mana_spent:float=0.
    qready:float=0.; charges:int=2; wready:float=0.; cs:int=0; gold_got:float=0.; xp_got:float=0.
    xp_area:float=0.; cd_area:float=0.; last_xp_time:float=0.; qstack:int=0; qlast:float=-100.
    aggro_until:float=0.; aggro_target:str|None=None
    commit_time:float=-1.

def dist(a,b):return math.hypot(a.x-b.x,a.y-b.y)
def line_distance(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]; den=dx*dx+dy*dy
    u=((p.x-a[0])*dx+(p.y-a[1])*dy)/max(den,1e-9)
    return math.hypot(p.x-(a[0]+max(0,min(1,u))*dx),p.y-(a[1]+max(0,min(1,u))*dy)),u

def particle(seed, nominal=False):
    rng=np.random.default_rng(seed)
    def r(a,b):return (a+b)/2 if nominal else float(rng.uniform(a,b))
    return dict(seed=seed,red_x=r(1800,2000),blue_x=r(-2000,-1800),spacing=r(135,175),
                lateral=[r(-70,70) for _ in range(12)],A_x=r(500,650),A_y=r(-350,-250),
                B_x=r(1800,2100),B_y=r(500,800),B_available=r(8.5,11.5),first=r(2,2.7),
                ap=r(1.36,1.41),aw=r(.19,.27),bp=r(1.38,1.60),bad=r(60,70),bhp=r(720,760),
                reaction=r(.08,.22),damage=r(.97,1.03),hp=[r(.99,1) for _ in range(12)],
                bregen=r(1.5,3.5),tie_jitter=[r(0,.04) for _ in range(12)])

class Wave:
    def __init__(self,p,setup=(0,0),opponent='q_secure',pressure=True,record=False,horizon=29.,
                 minion_hp_damage=True,legacy_aggro=True):
        self.p=p;self.setup=setup;self.opponent=opponent;self.pressure=pressure;self.record=record
        self.H=horizon;self.env=simpy.Environment();self.units={};self.events=[];self.frames=[]
        self.deaths=[];self.soldiers=[];self.pending=[];self.minion_hp_damage=minion_hp_damage
        self.legacy_aggro=legacy_aggro;self.setup_hits=[0,0];self.setup_targets=[None,None]
        self.free_attempts=0;self.pressure_hits=0;self.qcasts=0;self.wcasts=0
        self.decision_blocks=[];self.obs=[];self.first_actions=[];self.w_recharge_tail=0.
        for side in ['A','B']:
            for j in range(6):
                kind='melee' if j<3 else 'caster';d=CFG['historical_effective_parameters'][kind]
                ix=j+(0 if side=='A' else 6);x=p['blue_x']-j*p['spacing'] if side=='A' else p['red_x']+j*p['spacing']
                u=Unit(f'{side}_{kind[0]}{j%3+1}',side,kind,x,p['lateral'][ix],d['hp']*p['hp'][ix],d['hp'],
                       d['ad'],d['period'],d['windup'],d['range'],d['speed'],d['projectile_speed'],
                       d['current_hp_fraction'],d['gold'],d['xp_root'])
                self.units[u.id]=u
        self.units['A']=Unit('A','A','hero',p['A_x'],p['A_y'],660,660,56,p['ap'],p['aw'],525,335,2600,armor=25,mr=30,mana=345)
        self.units['B']=Unit('B','B','hero',p['B_x'],p['B_y'],p['bhp'],p['bhp'],p['bad'],p['bp'],.28,175,345,armor=33,mr=32)

    @property
    def t(self):return self.env.now
    def log(self,kind,source='',target='',**kw):
        if self.record:self.events.append(dict(t=round(self.t,6),kind=kind,source=source,target=target,**kw))
    def mins(self,side=None):return [u for u in self.units.values() if u.kind!='hero' and u.hp>0 and (side is None or u.side==side)]
    def delay(self,dt,fn,*args):
        def process():
            yield self.env.timeout(max(0,dt));fn(*args)
        return self.env.process(process())
    def move(self,u,x,y,dt=.1):
        d=math.hypot(x-u.x,y-u.y);f=min(1,u.speed*dt/max(d,1e-9))
        u.x+=(x-u.x)*f;u.y+=(y-u.y)*f;u.phase='walking'
    def damage(self,s,t,raw,magic=False,slayer=False):
        if t.hp<=0:return 0.
        if slayer and self.minion_hp_damage:raw+=s.beta*t.hp
        if s.kind!='hero' and t.kind=='hero':raw*=.55
        resist=t.mr if magic else t.armor
        amount=raw*100/(100+resist)*self.p['damage'];actual=min(t.hp,amount);t.hp=max(0,t.hp-amount)
        if t.kind=='hero':t.hp_gross+=actual
        self.log('impact',s.id,t.id,damage=amount,hp_after=t.hp)
        if t.hp<=0:
            self.log('death',s.id,t.id)
            if t.kind!='hero':
                receiver=self.units['B' if t.side=='A' else 'A'];xp=0.
                if receiver.hp>0 and dist(receiver,t)<=1500:
                    xp=t.xp*.95;receiver.xp_area+=receiver.xp_got*(self.t-receiver.last_xp_time)
                    receiver.last_xp_time=self.t;receiver.xp_got+=xp
                cs=int(s.kind=='hero' and s.side!=t.side)
                if cs:s.cs+=1;s.gold_got+=t.gold
                self.deaths.append(dict(t=self.t,id=t.id,killer=s.id,gold=t.gold if cs else 0,xp=xp,receiver=receiver.id,cs=cs))
                self.log('reward',receiver.id,t.id,xp=xp,gold=t.gold if cs else 0)
        return actual
    def aggro(self,h,target):
        for u in self.mins('B' if h.side=='A' else 'A'):
            if dist(u,h)>500:continue
            # Historical minion-attack priority is below an existing minion duel.
            if target.kind=='hero' or (self.legacy_aggro and u.target is None):
                u.aggro_target=h.id;u.aggro_until=self.t+2
    def committed(self,s,t,raw,magic=False,slayer=False,flight=0):
        item={'land':self.t+flight,'target':t.id,'raw':raw,'beta':s.beta if slayer else 0,'source':s.id}
        self.pending.append(item)
        def land():
            self.pending.remove(item)
            # A committed projectile survives its caster's death. No resurrection of target.
            self.damage(s,t,raw,magic,slayer)
        self.delay(flight,land)
    def select_minion_target(self,u):
        if u.aggro_until>self.t and u.aggro_target:
            h=self.units[u.aggro_target]
            if h.hp>0 and dist(u,h)<750:return h
        old=self.units.get(u.target)
        if old and old.hp>0 and old.kind!='hero':return old
        enemies=self.mins('B' if u.side=='A' else 'A')
        return min(enemies,key=lambda e:(dist(u,e),e.id)) if enemies else None
    def minion_loop(self,u,jitter):
        yield self.env.timeout(jitter)
        while self.t<self.H and u.hp>0:
            target=self.select_minion_target(u)
            if target is None:
                # Unopposed survivors march but do not disappear or count as denied XP.
                self.move(u,u.x+(100 if u.side=='A' else -100),u.y)
                yield self.env.timeout(.1);continue
            if u.target!=target.id:self.log('retarget',u.id,target.id)
            u.target=target.id
            if dist(u,target)>u.reach+35:
                self.move(u,target.x,target.y);yield self.env.timeout(.1);continue
            if self.t<u.ready:
                u.phase='recovery';yield self.env.timeout(min(.1,u.ready-self.t));continue
            start=self.t;u.phase='windup';u.commit_time=start+u.wind;self.log('windup',u.id,target.id)
            yield self.env.timeout(u.wind)
            if u.hp<=0:break
            if target.hp<=0:continue
            if dist(u,target)>u.reach+100:u.phase='cancelled';continue
            self.log('commit',u.id,target.id);u.ready=start+u.period;u.phase='recovery';u.commit_time=-1
            self.committed(u,target,u.ad,slayer=target.kind!='hero',flight=dist(u,target)/u.missile if u.missile else 0)
    def expected_hp(self,target,dt):
        hp=target.hp
        incoming=list(self.pending)
        # Conditional forecast of visible windups and next scheduled attacks.
        # These remain cancelable in the actual event loop.
        for u in self.mins('B' if target.side=='A' else 'A'):
            if u.target!=target.id or dist(u,target)>u.reach+35:continue
            commit=u.commit_time if u.phase=='windup' and u.commit_time>=self.t else max(self.t,u.ready)+u.wind
            land=commit+(dist(u,target)/u.missile if u.missile else 0)
            while land<=self.t+dt:
                incoming.append(dict(target=target.id,land=land,raw=u.ad,beta=u.beta if self.minion_hp_damage else 0));land+=u.period
        for e in sorted(incoming,key=lambda e:e['land']):
            if e['target']==target.id and e['land']<=self.t+dt:hp-=e['raw']+e['beta']*max(hp,0)
        # Only already committed attacks are certain; future attacks are not subtracted here.
        return hp
    def incoming_dps(self,target):
        return sum((u.ad+u.beta*target.hp)/u.period for u in self.mins('B' if target.side=='A' else 'A') if u.target==target.id and dist(u,target)<u.reach+100)
    def active_soldiers(self):return [s for s in self.soldiers if s['expires']>self.t]
    def mode(self,h,target):
        if h.id=='A':
            ss=[s for s in self.active_soldiers() if math.hypot(h.x-s['x'],h.y-s['y'])<=800 and math.hypot(target.x-s['x'],target.y-s['y'])<=350]
            if ss:return ('soldier',63.3,.23,ss[0])
        return ('aa',h.ad+(5 if h.id=='A' and target.kind!='hero' else 0),h.wind+(dist(h,target)/h.missile if h.missile else 0),None)
    def reachable(self,h,target,kind='aa'):
        return (h.id=='A' and self.mode(h,target)[0]=='soldier') or dist(h,target)<= (450 if kind=='q' else h.reach)+35
    def can_secure(self,h,target,kind='aa'):
        if kind=='q':d=20+1.05*h.ad;delay=.35
        else:_,d,delay,_=self.mode(h,target)
        hp=self.expected_hp(target,delay)
        return 0<hp<=d*self.p['damage']
    def hero_attack(self,h,target):
        mode,raw,delay,soldier=self.mode(h,target);start=self.t
        h.ready=start+h.period;h.phase='windup';self.aggro(h,target)
        self.log('hero_attack',h.id,target.id,mode=mode)
        if h.id=='A' and len(self.first_actions)<12:self.first_actions.append((round(start,3),target.id,mode))
        yield self.env.timeout(h.wind if mode=='aa' else .23)
        if h.hp<=0 or target.hp<=0:return
        if mode=='aa':self.committed(h,target,raw,flight=dist(h,target)/h.missile if h.missile else 0)
        else:
            self.committed(h,target,raw,magic=True)
            # Rank-one soldier secondary target factor, approximate line geometry.
            a=(soldier['x'],soldier['y']);dx,dy=target.x-a[0],target.y-a[1];d=max(1,math.hypot(dx,dy))
            b=(a[0]+dx/d*375,a[1]+dy/d*375)
            for other in self.units.values():
                if other.side==h.side or other.hp<=0 or other.id==target.id:continue
                dd,u=line_distance(other,a,b)
                if dd<=45 and 0<=u<=1:self.committed(h,other,raw*.25,magic=True)
        if target.kind=='hero':self.pressure_hits+=1
        h.phase='recovery'
    def cast_q(self,h,target):
        self.qcasts+=1;h.qready=self.t+3.7;h.qstack=(h.qstack if self.t-h.qlast<6 else 0)+1;h.qlast=self.t
        # Do not silently treat Q3 as Q1: wait for stacks to expire at two stacks.
        h.cd_area+=min(3.7,self.H-self.t);h.ready=max(h.ready,self.t+.35)
        a=(h.x,h.y);dx,dy=target.x-h.x,target.y-h.y;d=max(1,math.hypot(dx,dy));b=(h.x+dx/d*450,h.y+dy/d*450)
        self.log('q_cast','B',target.id)
        yield self.env.timeout(.35)
        if h.hp<=0:return
        for u in list(self.units.values()):
            if u.side==h.side or u.hp<=0:continue
            dd,along=line_distance(u,a,b)
            if dd<70 and 0<=along<=1:self.damage(h,u,20+1.05*h.ad)
    def w(self,h,target):
        if h.mana<40 or h.charges<=0 or self.t<h.wready:return False
        d=dist(h,target);f=min(1,525/max(1,d));x=h.x+(target.x-h.x)*f;y=h.y+(target.y-h.y)*f
        h.mana-=40;h.mana_spent+=40;h.charges-=1;h.wready=self.t+1.5
        recharge_at=max(self.t,self.w_recharge_tail)+10;self.w_recharge_tail=recharge_at
        h.cd_area+=min(recharge_at-self.t,self.H-self.t);h.ready=max(h.ready,self.t+.25);self.wcasts+=1
        self.soldiers.append(dict(x=x,y=y,expires=self.t+10))
        self.log('w_cast','A',target.id,x=x,y=y)
        self.delay(recharge_at-self.t,lambda:setattr(h,'charges',min(2,h.charges+1)))
        return True
    def safe_free(self,h):
        for m in self.mins('B'):
            if m.hp <= 70+self.incoming_dps(m)*(h.period+.35):return False
        return True
    def pressure_risk(self,target):
        a=self.units['A']
        if not self.pressure or a.hp<=0:return 0
        for s in self.active_soldiers():
            if math.hypot(s['x']-target.x,s['y']-target.y)<400:return 63.3/1.32
        return 56/1.33 if dist(a,target)<a.reach else 0
    def hero_loop(self,h):
        if h.id=='B':yield self.env.timeout(self.p['B_available'])
        else:yield self.env.timeout(self.p['first'])
        while self.t<self.H and h.hp>0:
            enemies=self.mins('B' if h.id=='A' else 'A')
            if not enemies:yield self.env.timeout(.1);continue
            if self.t<h.ready:
                yield self.env.timeout(min(.1,h.ready-self.t));continue
            candidates=[m for m in enemies if self.can_secure(h,m)]
            target=min(candidates,key=lambda m:(m.hp,-m.gold)) if candidates else None
            if h.id=='B':
                qlegal=self.opponent!='aa_only' and self.t>=h.qready and (h.qstack<2 or self.t-h.qlast>=6)
                qtargets=[m for m in enemies if qlegal and self.can_secure(h,m,'q')]
                qt=min(qtargets,key=lambda m:m.hp) if qtargets else None
                # Different reasonable responses; no branch is forced to miss a minion.
                if qt and self.reachable(h,qt,'q'):
                    yield from self.cast_q(h,qt);continue
                if target:
                    risk=self.pressure_risk(target);tolerance={'aa_only':25,'q_secure':50,'push':100}[self.opponent]
                    if risk>tolerance:
                        self.log('decline_exposure','B',target.id,risk=risk)
                        self.move(h,h.x+50,h.y+50);yield self.env.timeout(.1);continue
                if not target and self.opponent=='push':target=min(enemies,key=lambda m:(m.hp,dist(h,m)))
                if target is None:
                    nearest=min(enemies,key=lambda m:m.hp/max(1,self.incoming_dps(m)))
                    # Q user keeps a 400-unit approach, other users a melee approach.
                    desired=400 if qlegal else 160;d=dist(h,nearest)
                    if d>desired:self.move(h,nearest.x+(h.x-nearest.x)/max(d,1)*desired,nearest.y+(h.y-nearest.y)/max(d,1)*desired)
                    yield self.env.timeout(.1);continue
            else:
                if target is None:
                    # Setup is a conditional policy: nearest leading melee, then leading caster.
                    for k,kind in enumerate(['melee','caster']):
                        if self.setup_hits[k]>=self.setup[k]:continue
                        if self.setup_targets[k] is None:
                            group=[m for m in enemies if m.kind==kind]
                            if not group:self.setup_hits[k]=self.setup[k];continue
                            self.setup_targets[k]=min(group,key=lambda m:dist(h,m)).id
                        target=self.units[self.setup_targets[k]]
                        if target.hp<=0:self.setup_hits[k]=self.setup[k];target=None;continue
                        self.setup_hits[k]+=1;break
                    if target is None and self.pressure:
                        b=self.units['B']
                        if self.t>=self.p['B_available'] and dist(h,b)<900 and self.safe_free(h):
                            if not self.active_soldiers() and self.w(h,b):yield self.env.timeout(.25);continue
                            if self.reachable(h,b):
                                self.free_attempts+=1;yield from self.hero_attack(h,b);continue
                    if target is None:
                        nearest=min(enemies,key=lambda m:m.hp/max(1,self.incoming_dps(m)))
                        d=dist(h,nearest)
                        if d>480:self.move(h,nearest.x+(h.x-nearest.x)/max(1,d)*480,nearest.y+(h.y-nearest.y)/max(1,d)*480)
                        yield self.env.timeout(.1);continue
            if target is None:yield self.env.timeout(.1);continue
            if not self.reachable(h,target):
                self.move(h,target.x,target.y)
                # Setup counters count submitted attacks, not approach iterations.
                if h.id=='A':
                    for k,tid in enumerate(self.setup_targets):
                        if tid==target.id and not candidates:self.setup_hits[k]-=1
                yield self.env.timeout(.1);continue
            yield from self.hero_attack(h,target)
            yield self.env.timeout(self.p['reaction'])
    def observe(self):
        for t in [i*.5 for i in range(int(self.H*2)+1)]:
            yield self.env.timeout(max(0,t-self.t))
            a,b=self.units['A'],self.units['B']
            self.obs.append(dict(t=self.t,A_cs=a.cs,B_cs=b.cs,A_hp=a.hp,B_hp=b.hp,A_xp=a.xp_got,B_xp=b.xp_got))
            if self.record:
                for u in self.units.values():
                    self.frames.append(dict(t=self.t,id=u.id,x=u.x,y=u.y,hp=u.hp,maxhp=u.maxhp,target=u.target,phase=u.phase,ready=u.ready))
    def regeneration(self):
        last=0.
        while self.t<self.H:
            yield self.env.timeout(.1);dt=self.t-last;last=self.t
            for k,regen in [('A',1.4),('B',self.p['bregen'])]:
                h=self.units[k]
                if h.hp<=0:continue
                gain=min(h.maxhp-h.hp,regen*dt);h.hp+=gain;h.hp_healed+=gain
                if k=='A':h.mana=min(345,h.mana+2.5*dt)
    def run(self):
        for j,u in enumerate(self.mins()):self.env.process(self.minion_loop(u,self.p['tie_jitter'][j]))
        for k in ['A','B']:self.env.process(self.hero_loop(self.units[k]))
        self.env.process(self.observe());self.env.process(self.regeneration());self.env.run(until=self.H+1e-8)
        a,b=self.units['A'],self.units['B'];r=dict(seed=self.p['seed'],setup=f'{self.setup[0]}-{self.setup[1]}',opponent=self.opponent,pressure=self.pressure)
        for h in [a,b]:
            h.xp_area+=h.xp_got*(self.H-h.last_xp_time)
            pending=self.mins('B' if h.side=='A' else 'A')
            r.update({f'{h.id}_{k}':v for k,v in dict(cs=h.cs,gold=h.gold_got,xp=h.xp_got,xp_raw=h.xp_got/.95,
                xp_rate=h.xp_got/self.H,xp_area=h.xp_area,hp_loss=h.maxhp-h.hp,hp_gross=h.hp_gross,hp_healed=h.hp_healed,
                mana_spent=h.mana_spent,mana_end=h.mana,cd_area=h.cd_area,pending_xp=sum(u.xp*.95 for u in pending),
                pending_gold=sum(u.gold for u in pending),enemy_alive=len(pending)).items()})
        r.update(w_casts=self.wcasts,q_casts=self.qcasts,pressure_hits=self.pressure_hits)
        r['utility']=utility(r);r['first_A_cs']=next((d['t'] for d in self.deaths if d['killer']=='A'),None)
        r['first_B_cs']=next((d['t'] for d in self.deaths if d['killer']=='B'),None)
        r['completed_both_waves']=not self.mins()
        return r

def utility(r,wx=1.,wh=.5,wm=.25,wc=.1,tempo=0):
    # Relative resource score. Not a win probability; mana-less B has no mana cost.
    return ((r['A_gold']-r['B_gold'])/105 + wx*(r['A_xp']-r['B_xp'])/276.45
            +tempo*(r['A_xp_area']-r['B_xp_area'])/(29*276.45)
            +wh*(r['B_hp_loss']/740-r['A_hp_loss']/660)
            -wm*r['A_mana_spent']/345+wc*(r['B_cd_area']-r['A_cd_area'])/29)

def write_csv(path,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

if __name__=='__main__':
    for setup in [(0,0),(3,2)]:
        wave=Wave(particle(0,True),setup,record=True);print(json.dumps(wave.run(),indent=2))
