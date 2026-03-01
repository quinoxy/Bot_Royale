import json
import time
from enum import Enum


class Player(Enum):
    NONE = 0
    RED = 1
    BLUE = 2

class BoardCell:
    __slots__ = ('player','count')
    def __init__(self):
        self.player = Player.NONE
        self.count = 0

class Position:
    __slots__ = ('x','y')
    def __init__(self, x, y):
        self.x = x; self.y = y


# ============================================================
# TUNABLE WEIGHTS
# ============================================================
W_WIN = 10**9
W_CORNER_OWN = 50;  W_CORNER_OPP = -65;  W_CORNER_EMPTY = -6
W_EDGE_OWN = 8;     W_EDGE_OPP = -14;    W_EDGE_EMPTY = 0
W_EMPTY_MY = 0;     W_EMPTY_OPP = -2
W_EMPTY_MY_P = 2;   W_EMPTY_OPP_P = -6;  W_EMPTY_DOM = 1
W_COHESION = 6;     W_INFILTRATION = -7
W_SAFE_PRIMED = 16; W_DANGER_PRIMED = -22
W_RACE_LOSS = -30;  W_RACE_CRIT = -18
W_OVERPOWER = 38;   W_OVER_THRESH = 2
W_TOUCH_P = 8;      W_TOUCH_C = 14;      W_TOUCH_CP = 10
W_EXPL_OPP = 4;     W_EXPL_OPP_P = 6;    W_EXPL_EMPTY = -2
W_EXPL_FR_NO = -3;  W_EXPL_FR_YES = 2;   W_EXPL_WASTE = -5
W_DEV_BACKED = 8;   W_DEV_ISOLATED = -5;  W_CASCADE_RISK = -3
W_PATH_PRIMED = 5;  W_PATH_UNPRIMED = 2;  W_PATH_OPP = -4
W_PATH_OPP_P = -3;  W_PATH_BACKUP = 2;    W_EDGE_CONN = 2

# Development weights
W_SPREAD_PENALTY = -3   # per cell penalty when avg orbs too low
W_CONCENTRATION = 4     # per cell bonus when avg orbs high
W_STACK_QUADRATIC = 2   # quadratic stacking bonus multiplier


# ============================================================
# PRECOMPUTED BOARD INFO
# ============================================================
class BoardInfo:
    __slots__ = ('rows','cols','thresh','ote','is_corner','is_edge',
                 'my_p','opp_p','my_c','opp_c',
                 'my_adj','opp_adj','my_p_adj','opp_p_adj','my_c_adj','opp_c_adj',
                 'my_cells','opp_cells','my_orbs','opp_orbs',
                 'comp_str','max_str','opp_comp_str','opp_max_str',
                 'expl_val','phase','ew','dw','fortress',
                 'my_corners','opp_corners','free_corners')


def precompute(board, player, opponent):
    R, C = board.rows, board.cols
    dirs = ((-1,0),(1,0),(0,-1),(0,1))
    b = board.board
    I = BoardInfo()
    I.rows = R; I.cols = C

    thresh = [[0]*C for _ in range(R)]
    ote = [[0]*C for _ in range(R)]
    ic = [[False]*C for _ in range(R)]
    ie = [[False]*C for _ in range(R)]
    for i in range(R):
        for j in range(C):
            t = 4
            if i==0 or i==R-1: t-=1
            if j==0 or j==C-1: t-=1
            thresh[i][j]=t; ote[i][j]=t-b[i][j].count
            cr=(i==0 or i==R-1) and (j==0 or j==C-1)
            ic[i][j]=cr; ie[i][j]=(not cr) and (i==0 or i==R-1 or j==0 or j==C-1)
    I.thresh=thresh; I.ote=ote; I.is_corner=ic; I.is_edge=ie

    my_p=[[False]*C for _ in range(R)]; opp_p=[[False]*C for _ in range(R)]
    my_c=[[False]*C for _ in range(R)]; opp_c=[[False]*C for _ in range(R)]
    mc=oc=mo=oo=0
    for i in range(R):
        for j in range(C):
            p=b[i][j].player; t=ote[i][j]
            if p==player:
                mc+=1; mo+=b[i][j].count
                if t<=2: my_p[i][j]=True
                if t==1: my_c[i][j]=True
            elif p==opponent:
                oc+=1; oo+=b[i][j].count
                if t<=2: opp_p[i][j]=True
                if t==1: opp_c[i][j]=True
    I.my_p=my_p;I.opp_p=opp_p;I.my_c=my_c;I.opp_c=opp_c
    I.my_cells=mc;I.opp_cells=oc;I.my_orbs=mo;I.opp_orbs=oo

    ma=[[0]*C for _ in range(R)]; oa=[[0]*C for _ in range(R)]
    mpa=[[0]*C for _ in range(R)]; opa=[[0]*C for _ in range(R)]
    mca=[[0]*C for _ in range(R)]; oca=[[0]*C for _ in range(R)]
    for i in range(R):
        for j in range(C):
            m=o=mp=op=mcc=occ=0
            for dx,dy in dirs:
                ni,nj=i+dx,j+dy
                if 0<=ni<R and 0<=nj<C:
                    np=b[ni][nj].player
                    if np==player:
                        m+=1
                        if my_p[ni][nj]: mp+=1
                        if my_c[ni][nj]: mcc+=1
                    elif np==opponent:
                        o+=1
                        if opp_p[ni][nj]: op+=1
                        if opp_c[ni][nj]: occ+=1
            ma[i][j]=m;oa[i][j]=o;mpa[i][j]=mp;opa[i][j]=op;mca[i][j]=mcc;oca[i][j]=occ
    I.my_adj=ma;I.opp_adj=oa;I.my_p_adj=mpa;I.opp_p_adj=opa;I.my_c_adj=mca;I.opp_c_adj=oca

    par={}; sz={}; st={}
    def find(x):
        while par[x]!=x: par[x]=par[par[x]]; x=par[x]
        return x
    def union(a,b):
        ra,rb=find(a),find(b)
        if ra==rb: return
        if sz[ra]<sz[rb]: ra,rb=rb,ra
        par[rb]=ra; sz[ra]+=sz[rb]; st[ra]+=st[rb]

    for i in range(R):
        for j in range(C):
            if b[i][j].player==player:
                k=i*C+j; par[k]=k; sz[k]=1
                s=b[i][j].count + (8 if ic[i][j] else 3 if ie[i][j] else 0) + (5 if my_p[i][j] else 0)
                st[k]=s
    for i in range(R):
        for j in range(C):
            if b[i][j].player==player:
                for dx,dy in ((0,1),(1,0)):
                    ni,nj=i+dx,j+dy
                    if 0<=ni<R and 0<=nj<C and b[ni][nj].player==player: union(i*C+j,ni*C+nj)

    cs=[[0]*C for _ in range(R)]; ms=0
    for i in range(R):
        for j in range(C):
            if b[i][j].player==player:
                s=st[find(i*C+j)]; cs[i][j]=s
                if s>ms: ms=s
    I.comp_str=cs; I.max_str=ms

    opar={}; osz={}; ost={}
    def ofind(x):
        while opar[x]!=x: opar[x]=opar[opar[x]]; x=opar[x]
        return x
    def ounion(a,b):
        ra,rb=ofind(a),ofind(b)
        if ra==rb: return
        if osz[ra]<osz[rb]: ra,rb=rb,ra
        opar[rb]=ra; osz[ra]+=osz[rb]; ost[ra]+=ost[rb]

    for i in range(R):
        for j in range(C):
            if b[i][j].player==opponent:
                k=i*C+j; opar[k]=k; osz[k]=1
                s=b[i][j].count + (8 if ic[i][j] else 3 if ie[i][j] else 0) + (5 if opp_p[i][j] else 0)
                ost[k]=s
    for i in range(R):
        for j in range(C):
            if b[i][j].player==opponent:
                for dx,dy in ((0,1),(1,0)):
                    ni,nj=i+dx,j+dy
                    if 0<=ni<R and 0<=nj<C and b[ni][nj].player==opponent: ounion(i*C+j,ni*C+nj)

    ocs=[[0]*C for _ in range(R)]; oms=0
    for i in range(R):
        for j in range(C):
            if b[i][j].player==opponent:
                s=ost[ofind(i*C+j)]; ocs[i][j]=s
                if s>oms: oms=s
    I.opp_comp_str=ocs; I.opp_max_str=oms

    ev=[[0]*C for _ in range(R)]
    for i in range(R):
        for j in range(C):
            if not my_c[i][j]: continue
            v=0; occ=0; fh=0; eh=0
            for dx,dy in dirs:
                ni,nj=i+dx,j+dy
                if 0<=ni<R and 0<=nj<C:
                    np=b[ni][nj].player
                    if np==opponent:
                        occ+=1
                        if opp_p[ni][nj]: v+=W_EXPL_OPP_P
                    elif np==player:
                        fh+=1
                        if b[ni][nj].count==thresh[ni][nj]-1:
                            ht=False
                            for dx2,dy2 in dirs:
                                nni,nnj=ni+dx2,nj+dy2
                                if 0<=nni<R and 0<=nnj<C and b[nni][nnj].player==opponent: ht=True; break
                            v += W_EXPL_FR_YES if ht else W_EXPL_FR_NO
                    else: eh+=1
            v+=occ*W_EXPL_OPP+eh*W_EXPL_EMPTY
            if occ==0: v-=fh
            if occ==0 and fh==0: v+=W_EXPL_WASTE
            ev[i][j]=v
    I.expl_val=ev

    inc=vul=prc=se=0
    for i in range(R):
        for j in range(C):
            if b[i][j].player==player:
                if oa[i][j]>0: inc+=1
                if my_p[i][j]: prc+=1
                myote=ote[i][j]
                for dx,dy in dirs:
                    ni,nj=i+dx,j+dy
                    if 0<=ni<R and 0<=nj<C and b[ni][nj].player==opponent and ote[ni][nj]<myote:
                        vul+=1; break
            elif b[i][j].player==Player.NONE:
                hb=ht=False
                for dx,dy in dirs:
                    ni,nj=i+dx,j+dy
                    if 0<=ni<R and 0<=nj<C:
                        if my_p[ni][nj]: hb=True
                        if opp_p[ni][nj]: ht=True
                if hb and not ht: se+=1

    # Development-first strategy weights:
    # ew (expansion weight) is LOW — we don't want to expand blindly
    # dw (development weight) is HIGH — stack orbs on what we have
    ewv=0.3; dwv=2.0; fort=False
    if mc>0:
        cr_r=inc/mc; pr_r=prc/mc; vr=vul/mc; tr=mc/max(1,mc+oc)
        avg_orbs = mo / mc if mc > 0 else 0

        if cr_r>=0.8 and mc>=4: fort=True; dwv=2.4; ewv=0.2
        elif cr_r>=0.6 and mc>=3: fort=True; dwv=2.2; ewv=0.2
        if not fort:
            # Only increase expansion weight when we're well-developed
            if avg_orbs >= 2.0 and pr_r >= 0.5:
                # We're loaded — okay to expand a bit more
                ewv += 0.4
                dwv -= 0.2
            elif avg_orbs < 1.5 and mc >= 3:
                # Under-developed — double down on stacking
                ewv -= 0.1
                dwv += 0.4

            if vr>0.4: dwv+=0.4; ewv-=0.1
            elif vr>0.2: dwv+=0.2

            if tr<0.3: ewv+=0.15  # way behind in cells, expand a tiny bit
            elif tr>0.6: dwv+=0.2

        ewv=max(0.1,min(1.2,ewv)); dwv=max(1.0,min(3.0,dwv))
    I.ew=ewv; I.dw=dwv; I.fortress=fort

    corners=[(0,0),(0,C-1),(R-1,0),(R-1,C-1)]
    mcl=[];ocl=[];fcl=[]
    for ci,cj in corners:
        p=b[ci][cj].player
        if p==player: mcl.append((ci,cj))
        elif p==opponent: ocl.append((ci,cj))
        else: fcl.append((ci,cj))
    I.my_corners=mcl; I.opp_corners=ocl; I.free_corners=fcl
    tp=sum(b[i][j].count for i in range(R) for j in range(C) if b[i][j].player!=Player.NONE)
    if fcl and tp<R*C: I.phase=1
    elif len(mcl)>=2: I.phase=2
    else: I.phase=3

    return I


# ============================================================
# FAST EVALUATE
# ============================================================
def fast_evaluate(board, player, opponent):
    b = board.board; R = board.rows; C = board.cols
    dirs = ((-1,0),(1,0),(0,-1),(0,1))
    I = precompute(board, player, opponent)

    if I.opp_cells==0 and I.my_cells>0: return W_WIN
    if I.my_cells==0 and I.opp_cells>0: return -W_WIN
    if I.my_cells==0 and I.opp_cells==0: return 0

    score = 0; ew=I.ew; dw=I.dw; fort=I.fortress

    # === GLOBAL: punish thin spread, reward concentrated power ===
    if I.my_cells > 0:
        avg = I.my_orbs / I.my_cells
        if avg < 1.3 and I.my_cells >= 4:
            score += W_SPREAD_PENALTY * I.my_cells
        elif avg >= 2.0:
            score += W_CONCENTRATION * I.my_cells

    if I.phase==1:
        # Corner grabbing phase — corners are king
        for ci,cj in I.free_corners:
            thr=False
            for dx,dy in dirs:
                ni,nj=ci+dx,cj+dy
                if 0<=ni<R and 0<=nj<C and I.opp_p[ni][nj]: thr=True; break
            if not thr: score+=5  # free corner waiting for us
        score+=(len(I.my_corners)-len(I.opp_corners))*8

    if I.phase>=2 and len(I.my_corners)>=2:
        ec=set(); mcl=I.my_corners
        for ai in range(len(mcl)):
            for bi in range(ai+1,len(mcl)):
                a,bv=mcl[ai],mcl[bi]
                if a[0]==bv[0]:
                    for c in range(min(a[1],bv[1]),max(a[1],bv[1])+1): ec.add((a[0],c))
                elif a[1]==bv[1]:
                    for r in range(min(a[0],bv[0]),max(a[0],bv[0])+1): ec.add((r,a[1]))
                else:
                    for c in range(min(a[1],bv[1]),max(a[1],bv[1])+1): ec.add((a[0],c))
                    for r in range(min(a[0],bv[0]),max(a[0],bv[0])+1): ec.add((r,bv[1]))
        cs={(0,0),(0,C-1),(R-1,0),(R-1,C-1)}
        for pi,pj in ec:
            if (pi,pj) in cs: continue
            p=b[pi][pj].player
            if p==player:
                score+=int((W_PATH_PRIMED if I.my_p[pi][pj] else W_PATH_UNPRIMED)*(dw if I.my_p[pi][pj] else ew))
            elif p==opponent:
                score+=W_PATH_OPP+(W_PATH_OPP_P if I.opp_p[pi][pj] else 0)
            else:
                if I.my_p_adj[pi][pj]>0: score+=int(W_PATH_BACKUP*ew)

    for i in range(R):
        for j in range(C):
            c=b[i][j]; icr=I.is_corner[i][j]; ied=I.is_edge[i][j]
            ma=I.my_adj[i][j]; oa=I.opp_adj[i][j]
            mpa=I.my_p_adj[i][j]; opa=I.opp_p_adj[i][j]
            oca=I.opp_c_adj[i][j]; t=I.ote[i][j]
            thr=I.thresh[i][j]

            fm=1.0
            if fort:
                if c.player==player and I.max_str>0:
                    r=I.comp_str[i][j]/I.max_str; fm=0.2 if r<0.3 else 0.3+1.7*r
                elif c.player==opponent and I.opp_max_str>0:
                    r=I.opp_comp_str[i][j]/I.opp_max_str; fm=0.2 if r<0.3 else 0.3+1.7*r

            # --- Position value ---
            if icr:
                if c.player==player: score+=int(W_CORNER_OWN*fm)
                elif c.player==opponent: score+=int(W_CORNER_OPP*fm)
                else: score+=W_CORNER_EMPTY
            elif ied:
                if c.player==player: score+=int(W_EDGE_OWN*fm)
                elif c.player==opponent: score+=int(W_EDGE_OPP*fm)
                # Empty edges get ZERO — no incentive to rush and grab them
                # else: score+=W_EDGE_EMPTY

            # --- Empty cells: minimal value ---
            if c.player==Player.NONE:
                score+=W_EMPTY_MY*ma+W_EMPTY_OPP*oa+W_EMPTY_MY_P*mpa+W_EMPTY_OPP_P*opa
                if ma>oa: score+=W_EMPTY_DOM
                elif oa>ma: score-=W_EMPTY_DOM
                continue

            # --- Own cell: development is king ---
            if c.player==player:
                score+=int((W_COHESION*ma+W_INFILTRATION*oa)*fm)

                # Primed cell bonuses
                if I.my_p[i][j]:
                    score+=int((W_SAFE_PRIMED if oa==0 else W_DANGER_PRIMED)*fm)

                # === CORE DEVELOPMENT SCORING ===
                # Quadratic orb bonus: 1 orb=1, 2 orbs=4, 3 orbs=9
                # This HEAVILY rewards stacking over spreading
                score += int(W_STACK_QUADRATIC * c.count * c.count * fm)

                # Fill ratio bonus — how close to threshold
                fill = c.count / thr
                if fill >= 0.66:  # 2/3 full or more
                    score += int(10 * dw * fm)
                elif fill >= 0.5:
                    score += int(5 * dw * fm)
                elif c.count == 1 and not icr:
                    # Single orb in non-corner: barely developed
                    score += int(1 * fm)

                # Backed by primed friends = safe to develop
                if not I.my_p[i][j]:
                    if mpa > 0 and opa == 0:
                        score += int(W_DEV_BACKED * dw * fm)
                    elif ma == 0 and not icr:
                        score += int(W_DEV_ISOLATED * ew)

                # Developing near opponent = offensive pressure
                if oa > 0 and c.count >= thr - 2:
                    score += int(6 * dw * fm)

            # --- Opponent cells ---
            if c.player==opponent and I.opp_p[i][j] and mpa>0:
                dom=(2*mpa+ma)-(2*opa+oa)
                if dom>=W_OVER_THRESH: score+=int(W_OVERPOWER*mpa*fm)
                else:
                    score+=int(W_RACE_LOSS*mpa*fm)
                    if I.opp_c[i][j]: score+=int(W_RACE_CRIT*mpa*fm)

            if c.player==player and opa>0:
                max_os=0
                for dx,dy in dirs:
                    ni,nj=i+dx,j+dy
                    if 0<=ni<R and 0<=nj<C and I.opp_p[ni][nj]:
                        s=I.opp_comp_str[ni][nj]
                        if s>max_os: max_os=s
                if max_os>0:
                    cf=min(max_os/20.0,3.0)
                    min_opp_ote=99
                    for dx,dy in dirs:
                        ni,nj=i+dx,j+dy
                        if 0<=ni<R and 0<=nj<C and I.opp_p[ni][nj]:
                            if I.ote[ni][nj]<min_opp_ote: min_opp_ote=I.ote[ni][nj]
                    if t<min_opp_ote: score+=int(cf*3*fm)
                    elif oca>0:
                        score-=int(cf*4*fm)
                        mcs=I.comp_str[i][j]
                        if mcs>20: score-=int(min(mcs/20.0,3.0)*5*fm)

            if c.player==opponent:
                if I.opp_p[i][j] and ma>0: score+=int(W_TOUCH_P*fm)
                if I.opp_c[i][j] and ma>0:
                    score+=int(W_TOUCH_C*fm)
                    if mpa>0: score+=int(W_TOUCH_CP*fm)

            if c.player==player and I.my_c[i][j]:
                ev=I.expl_val[i][j]
                if ev>0: score+=int(ev*dw*fm)
                else: score+=int(ev*1.5)

            if c.player==player and not I.my_p[i][j] and opa>0 and mpa>0:
                score+=int(W_CASCADE_RISK*mpa*fm)

            # Opponent orbs are bad
            if c.player==opponent:
                score-=int(c.count*fm)

    score+=(I.my_cells-I.opp_cells)*1  # reduced — cell count matters less than orb count
    return score


# ============================================================
# BOARD CLASS
# ============================================================
class Board:
    def __init__(self, line):
        state = json.loads(line)
        self.rows = state['rows']; self.cols = state['cols']
        self.my_time = state['my_time']; self.opp_time = state['opp_time']
        self.me = state["player"]; self.move_number = state.get('move_number', 0)
        self.board = [[BoardCell() for _ in range(self.cols)] for _ in range(self.rows)]
        for i, row in enumerate(state['board']):
            for j, cd in enumerate(row):
                self.board[i][j].count = cd[0]
                self.board[i][j].player = Player(cd[1])

    def copy(self):
        nb = Board.__new__(Board)
        nb.rows=self.rows; nb.cols=self.cols
        nb.my_time=self.my_time; nb.opp_time=self.opp_time
        nb.me=self.me; nb.move_number=self.move_number
        nb.board=[[BoardCell() for _ in range(self.cols)] for _ in range(self.rows)]
        for i in range(self.rows):
            for j in range(self.cols):
                nb.board[i][j].player=self.board[i][j].player
                nb.board[i][j].count=self.board[i][j].count
        return nb

    def checkValidCell(self, x, y):
        return 0<=x<self.rows and 0<=y<self.cols

    def cellExploding(self, x, y):
        if not self.checkValidCell(x,y): return False
        t=4
        if x==0 or x==self.rows-1: t-=1
        if y==0 or y==self.cols-1: t-=1
        return self.board[x][y].count>=t

    def makeMove(self, x, y, player):
        if player==Player.NONE: return False
        if not self.checkValidCell(x,y): return False
        if self.board[x][y].player!=Player.NONE and self.board[x][y].player!=player: return False
        q=[(x,y)]
        while q:
            nq=[]
            for tx,ty in q:
                c=self.board[tx][ty]; c.count+=1; c.player=player
                if self.cellExploding(tx,ty):
                    c.count=0; c.player=Player.NONE
                    for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                        nx,ny=tx+dx,ty+dy
                        if self.checkValidCell(nx,ny): nq.append((nx,ny))
            q=nq
        return True

    def isTerminal(self, mc):
        if mc<2: return False
        r=b_=0
        for i in range(self.rows):
            for j in range(self.cols):
                p=self.board[i][j].player
                if p==Player.RED: r+=1
                elif p==Player.BLUE: b_+=1
        return r==0 or b_==0

    def evaluate(self, player):
        opponent = Player.RED if player==Player.BLUE else Player.BLUE
        return fast_evaluate(self, player, opponent)

    def getLegalMoves(self, player):
        moves=[]
        for i in range(self.rows):
            for j in range(self.cols):
                c=self.board[i][j]
                if c.player==Player.NONE or c.player==player:
                    moves.append((i,j))
        return moves


# ============================================================
# MOVE ORDERING — corners → develop → expand
# ============================================================
def order_moves(board, moves, player):
    """
    Three rigid phases:

    PHASE 1 — CORNERS (my_cells < ~4, free corners exist):
        Only free corners allowed. Stack if no corners left.

    PHASE 2 — EXPAND 3 (corners done or taken, my non-corner cells < 3):
        Place up to 3 cells on edges adjacent to our cells.
        Stacking existing cells is also fine.

    PHASE 3 — DEVELOP (non-corners >= 3, avg orbs < 1.8):
        ZERO expansion. Only stack existing cells.
        Build everything up toward threshold.

    PHASE 4 — NORMAL (avg orbs >= 1.8 or my_cells > 8):
        Original mid/late game logic. Expand cautiously,
        stack preferred, corners still top.
    """
    R=board.rows; C=board.cols
    b=board.board
    corners_pos=[(0,0),(0,C-1),(R-1,0),(R-1,C-1)]

    # --- Count state ---
    my_cells=0; my_orbs=0; my_corners=0
    free_corners=[]
    for i in range(R):
        for j in range(C):
            if b[i][j].player==player:
                my_cells+=1; my_orbs+=b[i][j].count
    for ci,cj in corners_pos:
        if b[ci][cj].player==player: my_corners+=1
        elif b[ci][cj].player==Player.NONE: free_corners.append((ci,cj))

    avg_orbs = my_orbs/my_cells if my_cells>0 else 0
    my_non_corners = my_cells - my_corners

    # --- Determine phase ---
    if free_corners and my_cells <= 6:
        phase = 1  # grab corners
    elif my_non_corners < 3:
        phase = 2  # expand 3 support cells
    elif avg_orbs < 1.8 and my_cells <= 10:
        phase = 3  # pure development, no expansion
    else:
        phase = 4  # normal play

    scored=[]
    for i,j in moves:
        s=0
        ic=(i==0 or i==R-1) and (j==0 or j==C-1)
        ie=(not ic) and (i==0 or i==R-1 or j==0 or j==C-1)
        c=b[i][j]
        t=4
        if i==0 or i==R-1: t-=1
        if j==0 or j==C-1: t-=1

        if c.player == player:
            # ===== OWN CELL: STACKING (welcome in all phases) =====
            orbs_to_boom = t - c.count

            if phase <= 2:
                # Early: stack but avoid pointless explosions
                s += 25
                if orbs_to_boom == 1:
                    has_opp = False
                    for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                        ni,nj=i+dx,j+dy
                        if 0<=ni<R and 0<=nj<C:
                            if b[ni][nj].player!=Player.NONE and b[ni][nj].player!=player:
                                has_opp=True; break
                    s += 35 if has_opp else 2  # don't waste an explosion early
                elif orbs_to_boom == 2:
                    s += 18
                else:
                    s += 10
                if ic: s += 6

            elif phase == 3:
                # DEVELOP PHASE: stacking is THE priority
                s += 30  # high base
                if orbs_to_boom == 1:
                    has_opp = False
                    for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                        ni,nj=i+dx,j+dy
                        if 0<=ni<R and 0<=nj<C:
                            if b[ni][nj].player!=Player.NONE and b[ni][nj].player!=player:
                                has_opp=True; break
                    s += 40 if has_opp else 5  # explode only if capturing
                elif orbs_to_boom == 2:
                    s += 25  # about to be critical — great
                else:
                    s += 15
                if ic: s += 10  # stacking corners in dev phase is great
                elif ie: s += 5

                # Bonus: near opponent = offensive buildup
                for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                    ni,nj=i+dx,j+dy
                    if 0<=ni<R and 0<=nj<C:
                        if b[ni][nj].player!=Player.NONE and b[ni][nj].player!=player:
                            s+=8; break

            else:
                # NORMAL PHASE: original logic
                s += 15
                if orbs_to_boom == 1:
                    has_opp = False
                    for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                        ni,nj=i+dx,j+dy
                        if 0<=ni<R and 0<=nj<C:
                            if b[ni][nj].player!=Player.NONE and b[ni][nj].player!=player:
                                has_opp=True; break
                    s += 40 if has_opp else 12
                elif orbs_to_boom == 2:
                    s += 20
                else:
                    s += 10
                if ic: s += 5
                elif ie: s += 3
                for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                    ni,nj=i+dx,j+dy
                    if 0<=ni<R and 0<=nj<C:
                        if b[ni][nj].player!=Player.NONE and b[ni][nj].player!=player:
                            s+=5; break

        elif c.player == Player.NONE:
            # ===== EMPTY CELL =====

            if ic:
                # FREE CORNER — top priority in phases 1-2, still good later
                threatened = False
                for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                    ni,nj=i+dx,j+dy
                    if 0<=ni<R and 0<=nj<C:
                        nc=b[ni][nj]
                        if nc.player!=Player.NONE and nc.player!=player:
                            nt=4
                            if ni==0 or ni==R-1: nt-=1
                            if nj==0 or nj==C-1: nt-=1
                            if nc.count >= nt-1:
                                threatened=True; break
                if phase == 1:
                    s += 80 if not threatened else 40  # corners are THE move
                elif phase == 2:
                    s += 70 if not threatened else 35
                elif phase == 3:
                    s += -100  # NO expansion in develop phase, not even corners
                else:
                    s += 55 if not threatened else 30

            elif phase == 1:
                # CORNER PHASE: non-corner expansion BLOCKED
                s += -100

            elif phase == 2:
                # EXPAND PHASE: allow edges adjacent to our cells
                adj_to_mine = False
                for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                    ni,nj=i+dx,j+dy
                    if 0<=ni<R and 0<=nj<C and b[ni][nj].player==player:
                        adj_to_mine=True; break
                if adj_to_mine and ie:
                    s += 12  # edge next to our cell — allowed
                elif adj_to_mine:
                    s += 6   # center next to our cell — less ideal
                else:
                    s += -100  # not adjacent — BLOCKED

            elif phase == 3:
                # DEVELOP PHASE: ALL expansion BLOCKED
                s += -100

            else:
                # NORMAL PHASE: cautious expansion
                has_primed_friend = False
                has_any_friend = False
                for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                    ni,nj=i+dx,j+dy
                    if 0<=ni<R and 0<=nj<C and b[ni][nj].player==player:
                        has_any_friend=True
                        nt=4
                        if ni==0 or ni==R-1: nt-=1
                        if nj==0 or nj==C-1: nt-=1
                        if b[ni][nj].count >= nt-2:
                            has_primed_friend=True; break
                if ie:
                    if has_primed_friend: s += 10
                    elif has_any_friend: s += 5
                    else: s += 1
                else:
                    if has_primed_friend: s += 6
                    elif has_any_friend: s += 3
                    else: s += 0

        scored.append((-s,i,j))
    scored.sort()
    return [(i,j) for _,i,j in scored]


# ============================================================
# TIME-MANAGED MINIMAX WITH ALPHA-BETA
# ============================================================
class TimeUp(Exception):
    pass

def minimax(board, depth, alpha, beta, maximizing, player, opponent, mc, deadline):
    if time.time() > deadline:
        raise TimeUp()

    if depth==0 or board.isTerminal(mc):
        return board.evaluate(player), None

    best_move = None

    if maximizing:
        max_eval = float('-inf')
        moves = order_moves(board, board.getLegalMoves(player), player)
        if not moves: return board.evaluate(player), None
        for mv in moves:
            nb=board.copy(); nb.makeMove(mv[0],mv[1],player)
            ev,_ = minimax(nb,depth-1,alpha,beta,False,player,opponent,mc+1,deadline)
            if ev>max_eval: max_eval=ev; best_move=mv
            alpha=max(alpha,ev)
            if beta<=alpha: break
        return max_eval, best_move
    else:
        min_eval = float('inf')
        moves = order_moves(board, board.getLegalMoves(opponent), opponent)
        if not moves: return board.evaluate(player), None
        for mv in moves:
            nb=board.copy(); nb.makeMove(mv[0],mv[1],opponent)
            ev,_ = minimax(nb,depth-1,alpha,beta,True,player,opponent,mc+1,deadline)
            if ev<min_eval: min_eval=ev; best_move=mv
            beta=min(beta,ev)
            if beta<=alpha: break
        return min_eval, best_move


def is_near_friendly(board, i, j, player, max_dist=2):
    """Check if (i,j) is within max_dist steps of any friendly cell."""
    R=board.rows; C=board.cols; b=board.board
    for di in range(-max_dist, max_dist+1):
        for dj in range(-max_dist, max_dist+1):
            if abs(di)+abs(dj) > max_dist: continue
            ni,nj=i+di,j+dj
            if 0<=ni<R and 0<=nj<C and b[ni][nj].player==player:
                return True
    return False

def is_in_enemy_zone(board, i, j, player):
    """
    Returns True if cell is closer to opponent mass than our mass.
    Prevents placing isolated cells in enemy territory.
    """
    R=board.rows; C=board.cols; b=board.board
    opponent = Player.RED if player==Player.BLUE else Player.BLUE

    # Find nearest friendly and nearest opponent (manhattan)
    min_friend=999; min_opp=999
    for r in range(R):
        for c in range(C):
            d=abs(r-i)+abs(c-j)
            if b[r][c].player==player and d<min_friend: min_friend=d
            elif b[r][c].player==opponent and d<min_opp: min_opp=d

    # Enemy zone = closer to opponent than to us, and not adjacent to us
    return min_friend > 2 and min_opp < min_friend


def filter_early_game(board, legal, player):
    """
    Hard-filter moves in early game so minimax CANNOT choose bad expansion.

    Phase 1 — PLACE 6 (my_cells < 6):
        Grab free corners first. Also allow edges/cells adjacent to
        our existing cells. Goal: establish 6 cells total.

    Phase 2 — DEVELOP (my_cells >= 6, avg_orbs < 1.8):
        ONLY stacking. Zero expansion. Build up the arsenal.

    Phase 3 — NORMAL (avg_orbs >= 1.8):
        Full move list, but ALWAYS filter out enemy-zone placements.
    """
    R=board.rows; C=board.cols
    b=board.board
    corners_pos=[(0,0),(0,C-1),(R-1,0),(R-1,C-1)]

    my_cells=0; my_orbs=0; my_corners=0
    free_corners=set()
    for i in range(R):
        for j in range(C):
            if b[i][j].player==player:
                my_cells+=1; my_orbs+=b[i][j].count
    for ci,cj in corners_pos:
        if b[ci][cj].player==player: my_corners+=1
        elif b[ci][cj].player==Player.NONE: free_corners.add((ci,cj))
    avg_orbs = my_orbs/my_cells if my_cells>0 else 0

    # Phase 1: Place up to 6 cells — corners first, then adjacent edges
    if my_cells < 6:
        allowed = []
        for i,j in legal:
            if b[i][j].player == player:
                allowed.append((i,j))  # stacking always ok
            elif (i,j) in free_corners:
                allowed.append((i,j))  # free corner — top priority
            elif b[i][j].player == Player.NONE:
                # allow only if adjacent to one of our cells
                adj=False
                for dx,dy in ((-1,0),(1,0),(0,-1),(0,1)):
                    ni,nj=i+dx,j+dy
                    if 0<=ni<R and 0<=nj<C and b[ni][nj].player==player:
                        adj=True; break
                if adj:
                    allowed.append((i,j))
        return allowed if allowed else legal

    # Phase 2: DEVELOP — only stacking, no expansion at all
    if avg_orbs < 1.8 and my_cells <= 12:
        allowed = []
        for i,j in legal:
            if b[i][j].player == player:
                allowed.append((i,j))
        # If all cells are at threshold and can't stack, fallback
        return allowed if allowed else legal

    # Phase 3: Normal — but never place in enemy territory
    allowed = []
    for i,j in legal:
        if b[i][j].player == player:
            allowed.append((i,j))  # stacking own cell — always fine
        elif b[i][j].player == Player.NONE:
            if (i,j) in free_corners:
                allowed.append((i,j))  # free corners always ok
            elif is_in_enemy_zone(board, i, j, player):
                continue  # SKIP: don't place isolated cells near enemy
            else:
                allowed.append((i,j))
    return allowed if allowed else legal


def getBestMove(board):
    player = Player.RED if board.me==1 else Player.BLUE
    opponent = Player.RED if player==Player.BLUE else Player.BLUE

    remaining = board.my_time / 1000.0
    estimated_moves_left = max(5, 30 - board.move_number // 2)
    time_budget = min(remaining / estimated_moves_left, remaining * 0.08)
    time_budget = max(time_budget, 0.005)
    deadline = time.time() + time_budget

    legal = board.getLegalMoves(player)
    if not legal: return None

    # Hard-filter: remove expansion moves in early game
    legal = filter_early_game(board, legal, player)

    if len(legal) == 1: return legal[0]

    best_move = legal[0]

    for depth in range(1, 20):
        try:
            _, mv = minimax(board, depth, float('-inf'), float('inf'),
                           True, player, opponent, board.move_number, deadline)
            if mv is not None:
                best_move = mv
        except TimeUp:
            break
        if time.time() > deadline - time_budget * 0.2:
            break

    return best_move


def play_move(row, col):
    print(f"{row} {col}", flush=True)


while True:
    line = input()
    board = Board(line)
    best = getBestMove(board)
    if best:
        play_move(best[0], best[1])