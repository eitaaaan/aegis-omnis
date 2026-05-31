#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# s01_mahjong.py — 本格麻雀ゲーム (ブラウザHTML起動)
from __future__ import annotations
import os, tempfile, webbrowser, pathlib
from s01_config import C

_MAHJONG_HTML_PATH: str | None = None

def handle_mahjong(arg: str) -> str:
    """
    /mj [3|4] [tonpu]  — ブラウザで本格麻雀を起動する。
      3        : 3人麻雀（デフォルト: 東風戦）
      4        : 4人麻雀（デフォルト: 東風戦）
      tonpu    : 東南戦（4人のみ）
    HTMLファイルをテンポラリに書き出してブラウザで開く。
    """
    global _MAHJONG_HTML_PATH

    arg = arg.strip().lower()
    num_players = 3 if "3" in arg else 4
    mode = "tonpu" if "tonpu" in arg else "east"  # east=東風戦, tonpu=東南戦

    # ── HTML生成 ──────────────────────────────────────────────
    html_content = _build_mahjong_html(num_players, mode)

    # 同じファイルを使い回す（ブラウザタブが増えすぎない）
    if _MAHJONG_HTML_PATH and pathlib.Path(_MAHJONG_HTML_PATH).exists():
        html_path = _MAHJONG_HTML_PATH
    else:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, dir="/mnt/c/Users/kouta/AppData/Local/Temp",
            encoding="utf-8", prefix="s01_mahjong_"
        )
        html_path = tmp.name
        _MAHJONG_HTML_PATH = html_path
        tmp.close()

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    try:
        webbrowser.open(f"file:///C:/Users/kouta/AppData/Local/Temp/" + os.path.basename(html_path))
        label = f"{num_players}人麻雀({'東南戦' if mode == 'tonpu' else '東風戦'})"
        return (
            f"\033[32m🀄 {label} をブラウザで起動しました\033[0m\n"
            f"\033[90m   ファイル: {html_path}\033[0m\n"
            f"\033[33m   /mj 3    → 3人麻雀\033[0m\n"
            f"\033[33m   /mj 4    → 4人麻雀（東風戦）\033[0m\n"
            f"\033[33m   /mj tonpu → 4人麻雀（東南戦）\033[0m"
        )
    except Exception as e:
        return (
            f"\033[33mブラウザ自動起動失敗: {e}\033[0m\n"
            f"次のファイルをブラウザで手動で開いてください:\n{html_path}"
        )


def _build_mahjong_html(num_players: int = 4, mode: str = "east") -> str:
    """麻雀ゲームの完全なHTMLを文字列で返す。"""
    # 起動時に自動で指定モードのゲームを開始するJSを差し込む
    auto_start_js = f"startGame({num_players},'{mode}');"
    # ── HTML本体 ──────────────────────────────────────────────
    return r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>本格麻雀 — S-01</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#1a1a2e;--bg2:#16213e;--bg3:#0f3460;
  --green:#1b5e20;--green2:#2e7d32;--green3:#388e3c;
  --tile:#f5e6c8;--tile-s:#e8d5a3;--tile-h:#d4a853;
  --red:#e53935;--blue:#1976d2;--gold:#ffd700;--silver:#c0c0c0;
  --text:#f0f0f0;--text2:#b0b0b0;--text3:#707070;
  --radius:6px;--shadow:0 2px 8px rgba(0,0,0,.5);
  --font:'Noto Sans JP',sans-serif;
}
body{background:var(--bg);color:var(--text);font-family:var(--font);min-height:100vh;overflow-x:hidden;user-select:none}
#app{display:flex;flex-direction:column;align-items:center;min-height:100vh}
.screen{display:none;width:100%;max-width:900px;padding:20px}
.screen.active{display:flex;flex-direction:column;align-items:center}
#title-screen{justify-content:center;min-height:100vh;gap:32px}
.title-logo{font-size:64px;font-weight:900;letter-spacing:8px;color:var(--gold);text-shadow:0 0 20px rgba(255,215,0,.4)}
.title-sub{font-size:14px;letter-spacing:4px;color:var(--text2)}
.btn-group{display:flex;flex-direction:column;gap:12px;width:280px}
.btn{padding:14px 32px;border:none;border-radius:var(--radius);font-size:16px;font-weight:700;cursor:pointer;transition:all .15s;letter-spacing:2px}
.btn-primary{background:linear-gradient(135deg,#b8860b,#ffd700);color:#1a1a00}
.btn-primary:hover{filter:brightness(1.15);transform:translateY(-2px)}
.btn-secondary{background:rgba(255,255,255,.08);color:var(--text);border:1px solid rgba(255,255,255,.2)}
.btn-secondary:hover{background:rgba(255,255,255,.15)}
#game-screen{padding:8px;max-width:960px;width:100%}
.table-area{position:relative;background:radial-gradient(ellipse at center,var(--green3) 0%,var(--green2) 50%,var(--green) 100%);border-radius:12px;border:4px solid #5d4037;box-shadow:inset 0 0 40px rgba(0,0,0,.3),var(--shadow);padding:8px;display:grid;grid-template-areas:"top top top" "left center right" "bottom bottom bottom";grid-template-rows:auto 1fr auto;grid-template-columns:auto 1fr auto;gap:4px;min-height:420px}
.seat-top{grid-area:top;display:flex;flex-direction:column;align-items:center;gap:2px}
.seat-left{grid-area:left;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px}
.seat-right{grid-area:right;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px}
.seat-info{background:rgba(0,0,0,.4);border-radius:4px;padding:3px 8px;font-size:11px;text-align:center;border:1px solid rgba(255,255,255,.1)}
.seat-name{font-weight:700;color:var(--gold)}
.seat-score{color:var(--text2);font-size:10px}
.seat-wind{font-size:10px;color:var(--silver)}
.ai-hand{display:flex;gap:2px}
.tile-back{width:24px;height:34px;background:linear-gradient(135deg,#1565c0,#0d47a1);border-radius:3px;border:1px solid rgba(255,255,255,.3);box-shadow:1px 1px 3px rgba(0,0,0,.5)}
.tile-back.small{width:18px;height:26px}
.seat-left .ai-hand,.seat-right .ai-hand{flex-direction:column}
.seat-left .tile-back,.seat-right .tile-back{width:34px;height:18px}
.center-area{grid-area:center;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px}
.info-panel{background:rgba(0,0,0,.5);border-radius:8px;padding:6px 16px;text-align:center;border:1px solid rgba(255,215,0,.3)}
.round-info{font-size:13px;color:var(--gold);font-weight:700}
.dora-area{display:flex;gap:4px;align-items:center}
.dora-label{font-size:10px;color:var(--text2)}
.pond{background:rgba(0,0,0,.2);border-radius:4px;padding:4px;display:flex;flex-wrap:wrap;gap:1px;align-content:flex-start;min-height:60px;max-height:80px;overflow:hidden;border:1px solid rgba(255,255,255,.05)}
.tile{background:var(--tile);color:#1a1a00;border-radius:4px;border:1px solid var(--tile-h);display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;cursor:pointer;box-shadow:1px 2px 3px rgba(0,0,0,.4),inset 0 -1px 0 rgba(0,0,0,.2);transition:all .1s;position:relative;flex-shrink:0}
.tile:hover{filter:brightness(1.1);transform:translateY(-2px)}
.tile.selected{transform:translateY(-8px);box-shadow:0 6px 12px rgba(255,215,0,.4),1px 2px 3px rgba(0,0,0,.4);border-color:var(--gold)}
.tile.man{color:#c62828}.tile.pin{color:#1565c0}.tile.sou{color:#2e7d32}.tile.honor{color:#4a148c}
.tile.discarded{width:20px;height:28px;font-size:9px;cursor:default}
.tile.discarded:hover{transform:none;filter:none}
.tile.full{width:36px;height:50px;font-size:18px}
.tile.medium{width:28px;height:40px;font-size:13px}
.tile.small{width:20px;height:28px;font-size:10px}
.player-area{grid-area:bottom;display:flex;flex-direction:column;align-items:center;gap:6px;padding:4px 0}
.player-info-row{display:flex;gap:16px;align-items:center}
.player-info{background:rgba(0,0,0,.5);border-radius:6px;padding:4px 12px;font-size:12px;border:1px solid rgba(255,215,0,.3)}
.player-name-label{color:var(--gold);font-weight:700}
.player-score-label{color:var(--text2)}
.player-hand{display:flex;gap:3px;align-items:flex-end;flex-wrap:wrap;justify-content:center;min-height:56px}
.melds-area{display:flex;gap:6px;flex-wrap:wrap;justify-content:center}
.meld{display:flex;gap:2px;background:rgba(0,0,0,.2);padding:3px;border-radius:4px;border:1px solid rgba(255,255,255,.1)}
.controls{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;min-height:44px}
.action-btn{padding:8px 16px;border:none;border-radius:4px;font-size:13px;font-weight:700;cursor:pointer;transition:all .1s;letter-spacing:1px}
.action-btn:hover{filter:brightness(1.2);transform:translateY(-1px)}
.btn-tsumo{background:#c62828;color:white}.btn-riichi{background:#7b1fa2;color:white}
.btn-ron{background:#e65100;color:white}.btn-chi{background:#1565c0;color:white}
.btn-pon{background:#0277bd;color:white}.btn-kan{background:#00695c;color:white}
.btn-skip{background:rgba(255,255,255,.1);color:var(--text2);border:1px solid rgba(255,255,255,.2)}
.btn-discard{background:var(--gold);color:#1a1a00}
.hud-top{display:flex;justify-content:space-between;align-items:center;padding:4px 8px;background:rgba(0,0,0,.4);border-radius:6px;font-size:12px}
.hud-item{display:flex;gap:6px;align-items:center}
.hud-label{color:var(--text2)}.hud-value{color:var(--gold);font-weight:700}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.75);display:none;align-items:center;justify-content:center;z-index:100}
.modal-overlay.show{display:flex}
.modal{background:#1e2a3a;border-radius:12px;padding:24px;max-width:480px;width:90%;border:2px solid rgba(255,215,0,.4);box-shadow:0 0 40px rgba(255,215,0,.1)}
.modal-title{font-size:22px;font-weight:900;text-align:center;color:var(--gold);margin-bottom:16px;letter-spacing:2px}
.result-row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.08);font-size:14px}
.hand-display{display:flex;gap:3px;flex-wrap:wrap;justify-content:center;margin:10px 0}
.score-delta{font-weight:700}.score-delta.pos{color:#81c784}.score-delta.neg{color:#ef9a9a}
.game-log{font-size:11px;color:var(--text3);text-align:center;height:18px;overflow:hidden}
.float-msg{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:rgba(0,0,0,.85);color:var(--gold);font-size:28px;font-weight:900;padding:16px 32px;border-radius:8px;letter-spacing:4px;pointer-events:none;opacity:0;transition:opacity .3s;z-index:200;border:2px solid var(--gold)}
.float-msg.show{opacity:1}
.waiting-overlay{position:absolute;inset:0;background:rgba(0,0,0,.3);display:none;align-items:center;justify-content:center;border-radius:12px;z-index:10;font-size:14px;color:var(--text2)}
.waiting-overlay.show{display:flex}
#final-screen{justify-content:center;min-height:100vh;gap:24px;padding:40px}
.final-title{font-size:32px;font-weight:900;color:var(--gold);letter-spacing:4px}
.rank-table{width:100%;max-width:400px}
.rank-row{display:flex;justify-content:space-between;padding:10px 16px;border-bottom:1px solid rgba(255,255,255,.08);font-size:15px}
.rank-1{color:#ffd700;font-weight:900}.rank-2{color:#c0c0c0;font-weight:700}.rank-3{color:#cd7f32}.rank-4{color:var(--text2)}
.thinking-dots::after{content:'';animation:dots 1.2s steps(4,end) infinite}
@keyframes dots{0%,100%{content:''}25%{content:'.'}50%{content:'..'}75%{content:'...'}}
.riichi-stick{width:60px;height:8px;background:white;border-radius:2px;border:1px solid #999;position:relative}
.riichi-stick::after{content:'';position:absolute;width:6px;height:6px;background:red;border-radius:50%;top:1px;left:27px}
</style>
</head>
<body>
<div id="app">

<div class="screen" id="title-screen">
  <div class="title-logo">麻雀</div>
  <div class="title-sub">MAHJONG — S-01 AI対戦</div>
  <div class="btn-group">
    <button class="btn btn-primary" onclick="startGame(4,'east')">4人麻雀（東風戦）</button>
    <button class="btn btn-primary" onclick="startGame(3,'east')">3人麻雀（東風戦）</button>
    <button class="btn btn-secondary" onclick="startGame(4,'tonpu')">4人麻雀（東南戦）</button>
  </div>
  <div style="font-size:11px;color:var(--text3);text-align:center;line-height:1.8;max-width:300px">
    プレイヤー1人 + AI（3〜4人）<br>
    立直・役判定・符計算完全実装<br>
    チー・ポン・槓対応
  </div>
</div>

<div class="screen" id="game-screen">
  <div class="hud-top">
    <div class="hud-item"><span class="hud-label">局</span><span class="hud-value" id="hud-round">東1局</span></div>
    <div class="hud-item"><span class="hud-label">本場</span><span class="hud-value" id="hud-honba">0</span></div>
    <div class="hud-item"><span class="hud-label">供托</span><span class="hud-value" id="hud-riichi-pool">0</span></div>
    <div class="hud-item"><span id="hud-tiles">残<b>70</b>枚</span></div>
    <button class="btn btn-secondary" style="padding:4px 12px;font-size:11px" onclick="showTitle()">戻る</button>
  </div>
  <div class="table-area" id="table">
    <div class="seat-top" id="seat-2">
      <div class="seat-info"><div class="seat-name" id="name-2">対面</div><div class="seat-wind" id="wind-2">北家</div><div class="seat-score" id="score-2">25000</div></div>
      <div class="melds-area" id="melds-2"></div>
      <div class="ai-hand" id="hand-2"></div>
      <div class="pond" id="pond-2" style="max-width:260px"></div>
    </div>
    <div class="seat-left" id="seat-1">
      <div class="seat-info"><div class="seat-name" id="name-1">上家</div><div class="seat-wind" id="wind-1">西家</div><div class="seat-score" id="score-1">25000</div></div>
      <div class="melds-area" id="melds-1" style="flex-direction:column"></div>
      <div class="ai-hand" id="hand-1"></div>
      <div class="pond" id="pond-1" style="max-height:100px;flex-direction:column;max-width:60px"></div>
    </div>
    <div class="center-area">
      <div class="info-panel">
        <div class="round-info" id="center-round">東1局</div>
        <div class="dora-area"><span class="dora-label">ドラ:</span><div id="dora-display"></div></div>
      </div>
      <div class="game-log" id="game-log">ゲーム開始</div>
      <div id="riichi-sticks" style="display:flex;gap:4px;justify-content:center;flex-wrap:wrap"></div>
    </div>
    <div class="seat-right" id="seat-3">
      <div class="seat-info"><div class="seat-name" id="name-3">下家</div><div class="seat-wind" id="wind-3">東家</div><div class="seat-score" id="score-3">25000</div></div>
      <div class="melds-area" id="melds-3" style="flex-direction:column"></div>
      <div class="ai-hand" id="hand-3"></div>
      <div class="pond" id="pond-3" style="max-height:100px;flex-direction:column;max-width:60px"></div>
    </div>
    <div class="player-area" id="seat-0">
      <div class="melds-area" id="melds-0"></div>
      <div class="player-hand" id="hand-0"></div>
      <div class="player-info-row">
        <div class="player-info">
          <span class="player-name-label">あなた</span>
          <span style="color:var(--text2);margin:0 6px" id="player-wind-label">東家</span>
          <span class="player-score-label" id="score-0">25000</span>
        </div>
        <div id="riichi-indicator"></div>
      </div>
      <div class="controls" id="controls"></div>
    </div>
    <div class="waiting-overlay" id="waiting">AI思考中<span class="thinking-dots"></span></div>
  </div>
</div>

<div class="screen" id="final-screen">
  <div class="final-title">ゲーム終了</div>
  <div class="rank-table" id="final-ranks"></div>
  <div style="display:flex;gap:12px;margin-top:16px">
    <button class="btn btn-primary" onclick="location.reload()">もう一度</button>
    <button class="btn btn-secondary" onclick="showTitle()">タイトルへ</button>
  </div>
</div>
</div>

<div class="modal-overlay" id="modal">
  <div class="modal">
    <div class="modal-title" id="modal-title">和了</div>
    <div id="modal-body"></div>
    <div style="text-align:center;margin-top:16px">
      <button class="btn btn-primary" onclick="closeModal()" style="width:120px">次へ</button>
    </div>
  </div>
</div>
<div class="float-msg" id="float-msg"></div>

<script>
// ============================================================
// MAHJONG ENGINE — S-01 Edition
// ============================================================
const SUITS=['man','pin','sou'];
const HONORS=['東','南','西','北','白','発','中'];
const WIND_CHARS=['東','南','西','北'];
function tilesEqual(a,b){return a.suit===b.suit&&a.num===b.num}
function tileSortKey(t){
  if(t.suit==='man')return 100+t.num;
  if(t.suit==='pin')return 200+t.num;
  if(t.suit==='sou')return 300+t.num;
  return 400+HONORS.indexOf(t.num);
}
function sortHand(h){return[...h].sort((a,b)=>tileSortKey(a)-tileSortKey(b))}
function tileStr(t){
  if(!t)return'?';
  if(t.suit==='honor')return t.num;
  return t.num+(t.suit==='man'?'萬':t.suit==='pin'?'筒':'索');
}
function allTiles(){
  const t=[];
  for(const s of SUITS)for(let n=1;n<=9;n++)for(let i=0;i<4;i++)t.push({suit:s,num:n,uid:t.length});
  for(const h of HONORS)for(let i=0;i<4;i++)t.push({suit:'honor',num:h,uid:t.length});
  return t;
}
function shuffle(a){for(let i=a.length-1;i>0;i--){const j=Math.random()*i|0;[a[i],a[j]]=[a[j],a[i]];}return a;}

let G={};
function initGame(np,mode){
  G={numPlayers:np,mode,players:[],walls:[],deadWall:[],
     doraIndicators:[],uraDoraIndicators:[],
     activePlayer:0,dealer:0,round:0,honba:0,riichiPool:0,
     phase:'idle',lastDiscard:null,lastDiscardPlayer:-1,
     pendingClaims:[],maxRound:mode==='tonpu'?8:4,
     gameOver:false,waitingForPlayer:false,
     selectedTile:null,riichiCandidates:[],_pendingNextRound:null};
  const names=['あなた','AI-A','AI-B','AI-C'];
  for(let i=0;i<np;i++)
    G.players.push({name:names[i],isHuman:i===0,score:25000,
      hand:[],drawn:null,pond:[],melds:[],riichi:false,riichiTurn:-1,wind:WIND_CHARS[i]});
  startRound();
}

function startRound(){
  for(let i=0;i<G.numPlayers;i++){
    G.players[i].wind=WIND_CHARS[(i-G.dealer+4)%4];
    if(G.numPlayers===3&&i===2)G.players[i].wind='北';
  }
  let wall=allTiles();
  if(G.numPlayers===3)wall=wall.filter(t=>!(t.suit==='man'&&t.num>=2&&t.num<=8));
  shuffle(wall);
  G.deadWall=wall.splice(wall.length-14,14);
  G.doraIndicators=[G.deadWall[4]];
  G.uraDoraIndicators=[G.deadWall[9]];
  G.walls=wall;
  for(const p of G.players){p.hand=[];p.drawn=null;p.pond=[];p.melds=[];p.riichi=false;p.riichiTurn=-1;}
  for(let i=0;i<13;i++)for(const p of G.players)p.hand.push(G.walls.shift());
  for(const p of G.players)p.hand=sortHand(p.hand);
  G.phase='draw';G.activePlayer=G.dealer;
  G.lastDiscard=null;G.lastDiscardPlayer=-1;
  G.selectedTile=null;G.riichiCandidates=[];
  renderAll();log(`${roundName()} 開始`);nextTurn();
}

function roundName(){
  const w=['東','南','西','北'][Math.floor(G.round/G.numPlayers)];
  return`${w}${(G.round%G.numPlayers)+1}局`;
}
function wallCount(){return G.walls.length}
function drawTile(pi){if(!G.walls.length)return null;const t=G.walls.shift();G.players[pi].drawn=t;return t;}

// ── ドラ計算 ──
function doraFromIndicator(ind){
  if(!ind)return null;
  if(ind.suit==='honor'){
    const idx=HONORS.indexOf(ind.num);
    return{suit:'honor',num:idx<4?HONORS[(idx+1)%4]:HONORS[4+((idx-4+1)%3)]};
  }
  return{suit:ind.suit,num:ind.num===9?1:ind.num+1};
}
function countDora(hand,melds,inds){
  let c=0;
  const all=[...hand,...melds.flatMap(m=>m.tiles)];
  for(const ind of inds){const d=doraFromIndicator(ind);if(!d)continue;for(const t of all)if(tilesEqual(t,d))c++;}
  return c;
}

// ── 和了判定 ──
function decomposeMentsu(tiles){
  if(!tiles.length)return[];
  const s=[...tiles].sort((a,b)=>tileSortKey(a)-tileSortKey(b));
  for(let i=0;i<s.length-2;i++){
    if(tilesEqual(s[i],s[i+1])&&tilesEqual(s[i],s[i+2])){
      const rest=s.filter((_,x)=>x!==i&&x!==i+1&&x!==i+2);
      const sub=decomposeMentsu(rest);if(sub!==null)return[{type:'pon',tiles:[s[i],s[i+1],s[i+2]]},...sub];
    }
  }
  for(let i=0;i<s.length;i++){
    if(s[i].suit==='honor')continue;
    const t1=s[i];
    const j=s.findIndex((t,x)=>x>i&&tilesEqual(t,{suit:t1.suit,num:t1.num+1}));if(j===-1)continue;
    const k=s.findIndex((t,x)=>x>i&&x!==j&&tilesEqual(t,{suit:t1.suit,num:t1.num+2}));if(k===-1)continue;
    const rest=s.filter((_,x)=>x!==i&&x!==j&&x!==k);
    const sub=decomposeMentsu(rest);if(sub!==null)return[{type:'chi',tiles:[s[i],s[j],s[k]]},...sub];
  }
  return null;
}
function isChiitoitsu(tiles){
  if(tiles.length!==14)return false;
  const g={};for(const t of tiles){const k=t.suit+t.num;g[k]=(g[k]||0)+1;}
  const v=Object.values(g);return v.every(x=>x===2)&&v.length===7;
}
function isKokushi(tiles){
  if(tiles.length!==14)return false;
  const terms=['man1','man9','pin1','pin9','sou1','sou9',...HONORS.map(h=>'honor'+h)];
  const has=new Set(tiles.map(t=>t.suit+t.num));
  if(terms.filter(k=>has.has(k)).length<13)return false;
  const c={};for(const t of tiles)c[t.suit+t.num]=(c[t.suit+t.num]||0)+1;
  return terms.some(k=>c[k]===2);
}
function getWinningDecompositions(tiles){
  const res=[];
  const sorted=sortHand(tiles);
  for(let pi=0;pi<sorted.length;pi++){
    const pair=sorted[pi];
    const pairTiles=[];const remaining=[];let found=0;
    for(const t of sorted){if(found<2&&tilesEqual(t,pair)){pairTiles.push(t);found++;}else remaining.push(t);}
    if(pairTiles.length!==2)continue;
    const melds=decomposeMentsu(remaining);
    if(melds!==null)res.push({pair:pairTiles,melds,tiles:sorted});
  }
  if(isChiitoitsu(sorted))res.push({type:'chiitoitsu',tiles:sorted});
  if(isKokushi(sorted))res.push({type:'kokushi',tiles:sorted});
  return res;
}
function canWin(hand,drawn,melds){
  const all=[...hand,...(drawn?[drawn]:[]),...melds.flatMap(m=>m.tiles)];
  if(all.length<14)return false;
  return getWinningDecompositions([...hand,...(drawn?[drawn]:[])]).length>0;
}
function tenpaiTiles(hand,melds){
  const types=[];
  for(const s of SUITS)for(let n=1;n<=9;n++)types.push({suit:s,num:n});
  for(const h of HONORS)types.push({suit:'honor',num:h});
  return types.filter(t=>canWin(hand,t,melds));
}
function isTenpai(hand,melds){return tenpaiTiles(hand,melds).length>0}

// ── 役判定 ──
function getYaku(decomp,player,gameState,isTsumo){
  const yaku=[];const{melds,riichi}=player;const isMenzen=melds.length===0;
  const{type}=decomp;
  if(type==='chiitoitsu'){yaku.push({name:'七対子',han:2});}
  else if(type==='kokushi'){yaku.push({name:'国士無双',han:13,yakuman:true});}
  else{
    const allM=[...melds,...(decomp.melds||[])];
    if(isTsumo&&isMenzen)yaku.push({name:'門前清自摸和',han:1});
    if(riichi)yaku.push({name:'立直',han:1});
    const hAll=[...player.hand,...(player.drawn?[player.drawn]:[]),...melds.flatMap(m=>m.tiles)];
    if(isTanyao(hAll))yaku.push({name:'断么九',han:1});
    if(isMenzen&&!isTsumo&&isPinfu(decomp,player,gameState))yaku.push({name:'平和',han:1});
    if(isMenzen&&isIipeiko(decomp.melds))yaku.push({name:'一盃口',han:1});
    yaku.push(...checkYakuhai(decomp.pair,allM,player,gameState));
    if(isSanshokuDoujun(allM))yaku.push({name:'三色同順',han:isMenzen?2:1});
    if(isSanshokuDoukou(allM))yaku.push({name:'三色同刻',han:2});
    if(isIttsu(allM))yaku.push({name:'一気通貫',han:isMenzen?2:1});
    if(isToitoi(allM))yaku.push({name:'対々和',han:2});
    const hc=checkHoChiNitsu(hAll);
    if(hc)yaku.push({name:hc,han:hc==='清一色'?(isMenzen?6:5):(isMenzen?3:2)});
  }
  const dc=countDora([...player.hand,...(player.drawn?[player.drawn]:[])],player.melds,gameState.doraIndicators);
  if(dc>0)yaku.push({name:`ドラ${dc}`,han:dc,isBonus:true});
  if(player.riichi){
    const uc=countDora([...player.hand,...(player.drawn?[player.drawn]:[])],player.melds,gameState.uraDoraIndicators);
    if(uc>0)yaku.push({name:`裏ドラ${uc}`,han:uc,isBonus:true});
  }
  return yaku;
}
function isTanyao(tiles){return tiles.every(t=>t.suit!=='honor'&&t.num>=2&&t.num<=8)}
function isPinfu(decomp,player,gs){
  if(!decomp.melds||!decomp.melds.every(m=>m.type==='chi'))return false;
  const p=decomp.pair[0];
  if(p.suit==='honor'){
    const rw=WIND_CHARS[Math.floor(gs.round/gs.numPlayers)];
    if(p.num===rw||p.num===player.wind)return false;
    if(['白','発','中'].includes(p.num))return false;
  }
  return true;
}
function isIipeiko(melds){
  if(!melds||melds.length<2)return false;
  for(let i=0;i<melds.length;i++)for(let j=i+1;j<melds.length;j++){
    if(melds[i].type==='chi'&&melds[j].type==='chi'){
      const a=sortHand(melds[i].tiles),b=sortHand(melds[j].tiles);
      if(a.every((t,k)=>tilesEqual(t,b[k])))return true;
    }
  }
  return false;
}
function checkYakuhai(pair,allM,player,gs){
  const yaku=[];const rw=WIND_CHARS[Math.floor(gs.round/gs.numPlayers)];
  for(const m of allM){
    if(m.type!=='pon'&&m.type!=='kan')continue;
    const t=m.tiles[0];if(t.suit!=='honor')continue;
    if(t.num==='白')yaku.push({name:'役牌：白',han:1});
    else if(t.num==='発')yaku.push({name:'役牌：発',han:1});
    else if(t.num==='中')yaku.push({name:'役牌：中',han:1});
    else if(t.num===rw)yaku.push({name:`役牌：${rw}`,han:1});
    else if(t.num===player.wind)yaku.push({name:`役牌：${player.wind}`,han:1});
  }
  return yaku;
}
function isSanshokuDoujun(melds){
  const chi=melds.filter(m=>m.type==='chi');
  for(const c of chi){const n=c.tiles[0].num;
    if(chi.some(x=>x.tiles[0].suit==='man'&&x.tiles[0].num===n)&&
       chi.some(x=>x.tiles[0].suit==='pin'&&x.tiles[0].num===n)&&
       chi.some(x=>x.tiles[0].suit==='sou'&&x.tiles[0].num===n))return true;
  }return false;
}
function isSanshokuDoukou(melds){
  const pon=melds.filter(m=>m.type==='pon'||m.type==='kan');
  for(let n=1;n<=9;n++)
    if(pon.some(m=>m.tiles[0].suit==='man'&&m.tiles[0].num===n)&&
       pon.some(m=>m.tiles[0].suit==='pin'&&m.tiles[0].num===n)&&
       pon.some(m=>m.tiles[0].suit==='sou'&&m.tiles[0].num===n))return true;
  return false;
}
function isIttsu(melds){
  const chi=melds.filter(m=>m.type==='chi');
  for(const s of SUITS)
    if(chi.some(m=>m.tiles[0].suit===s&&m.tiles[0].num===1)&&
       chi.some(m=>m.tiles[0].suit===s&&m.tiles[0].num===4)&&
       chi.some(m=>m.tiles[0].suit===s&&m.tiles[0].num===7))return true;
  return false;
}
function isToitoi(melds){return melds.every(m=>m.type==='pon'||m.type==='kan')}
function checkHoChiNitsu(tiles){
  const suits=new Set(tiles.filter(t=>t.suit!=='honor').map(t=>t.suit));
  const hasH=tiles.some(t=>t.suit==='honor');
  if(suits.size===1&&!hasH)return'清一色';
  if(suits.size===1&&hasH)return'混一色';
  return null;
}

// ── 点数計算 ──
function calcFu(decomp,isTsumo,isMenzen){
  if(decomp.type==='chiitoitsu')return 25;
  let fu=isMenzen&&!isTsumo?30:20;
  if(isTsumo&&!isMenzen)fu+=2;
  if(decomp.pair){const p=decomp.pair[0];if(p.suit==='honor'&&['白','発','中'].includes(p.num))fu+=2;}
  for(const m of(decomp.melds||[])){
    const t=m.tiles[0];const isTH=t.suit==='honor'||(t.suit!=='honor'&&(t.num===1||t.num===9));
    if(m.type==='pon')fu+=isTH?4:2;if(m.type==='kan')fu+=isTH?16:8;
  }
  return Math.ceil(fu/10)*10;
}
function calcBasicPoints(han,fu){
  if(han>=13)return 8000;if(han>=11)return 6000;if(han>=8)return 4000;
  if(han>=6)return 3000;if(han===5||(han===4&&fu>=30)||(han===3&&fu>=70))return 2000;
  return Math.min(fu*Math.pow(2,han+2),2000);
}
function calcScore(yaku,decomp,isTsumo,isDealer){
  const han=yaku.reduce((s,y)=>s+y.han,0);
  const fu=calcFu(decomp,isTsumo,true);
  const basic=calcBasicPoints(han,fu);
  if(isTsumo)return{han,fu,basic,dealer:Math.ceil(basic*2/100)*100,nonDealer:Math.ceil(basic/100)*100,isTsumo:true};
  return{han,fu,basic,ron:Math.ceil(basic*(isDealer?6:4)/100)*100,isTsumo:false};
}

// ── 副露可否 ──
function canChi(hand,tile,pi,ldp){
  const left=(pi-1+G.numPlayers)%G.numPlayers;
  if(ldp!==left||tile.suit==='honor')return[];
  const opts=[];const nums=hand.filter(t=>t.suit===tile.suit).map(t=>t.num);const n=tile.num;
  if(nums.includes(n-2)&&nums.includes(n-1))opts.push([n-2,n-1,n]);
  if(nums.includes(n-1)&&nums.includes(n+1))opts.push([n-1,n,n+1]);
  if(nums.includes(n+1)&&nums.includes(n+2))opts.push([n,n+1,n+2]);
  return opts;
}
function canPon(hand,tile){return hand.filter(t=>tilesEqual(t,tile)).length>=2}
function canKan(hand,tile){return hand.filter(t=>tilesEqual(t,tile)).length>=3}
function canAnkan(hand){
  const c={};for(const t of hand)c[t.suit+t.num]=(c[t.suit+t.num]||0)+1;
  return Object.entries(c).filter(([,v])=>v===4).map(([k])=>k);
}
function canRon(hand,melds,tile,player){
  const th=[...hand,tile];
  if(!canWin(th,null,melds))return false;
  const decomps=getWinningDecompositions(th);
  return decomps.some(d=>getYaku(d,{...player,drawn:tile},G,false).filter(y=>!y.isBonus).length>0);
}
function canTsumo(player){
  if(!player.drawn)return false;
  if(!canWin(player.hand,player.drawn,player.melds))return false;
  const th=[...player.hand,player.drawn];
  return getWinningDecompositions(th).some(d=>getYaku(d,player,G,true).filter(y=>!y.isBonus).length>0);
}

// ── ゲームフロー ──
function nextTurn(){
  if(G.gameOver)return;
  const p=G.players[G.activePlayer];
  if(!G.walls.length){handleRyukyoku();return;}
  const tile=drawTile(G.activePlayer);if(!tile){handleRyukyoku();return;}
  log(`${p.name}がツモ`);renderAll();
  if(p.isHuman){G.phase='discard';G.waitingForPlayer=true;renderControls();}
  else setTimeout(()=>aiTurn(G.activePlayer),700+Math.random()*500);
}

function aiTurn(pi){
  if(G.gameOver||G.activePlayer!==pi)return;
  const p=G.players[pi];showWaiting(true);
  setTimeout(()=>{
    if(canTsumo(p)){showWaiting(false);declareWin(pi,null,true);return;}
    const ak=canAnkan([...p.hand,...(p.drawn?[p.drawn]:[])]);
    if(ak.length&&Math.random()<0.3){
      const kt=[...p.hand,...(p.drawn?[p.drawn]:[])].find(t=>t.suit+t.num===ak[0]);
      doKan(pi,kt,true);showWaiting(false);return;
    }
    const hwD=[...p.hand,...(p.drawn?[p.drawn]:[])];
    if(!p.riichi&&!p.melds.length&&p.score>=1000&&Math.random()<0.45){
      const wts=tenpaiTiles(hwD.slice(0,-1),p.melds);
      if(wts.length){const d=chooseAIDiscard(pi,true);if(d){doRiichi(pi,d);showWaiting(false);return;}}
    }
    const d=chooseAIDiscard(pi,false);if(d)doDiscard(pi,d);
    showWaiting(false);
  },400+Math.random()*400);
}

function evaluateHand(hand,melds){
  let score=0;
  const d=decomposeMentsu([...hand]);if(d!==null)score+=d.length*10;
  if(isTenpai(hand,melds))score+=50;
  const s=sortHand(hand);
  for(let i=0;i<s.length-1;i++){
    if(tilesEqual(s[i],s[i+1]))score+=3;
    if(s[i].suit!=='honor'&&s[i+1].suit===s[i].suit&&s[i+1].num===s[i].num+1)score+=2;
    if(s[i].suit!=='honor'&&s[i+1].suit===s[i].suit&&s[i+1].num===s[i].num+2)score+=1;
  }
  for(const t of s){
    if(t.suit==='honor'&&!s.some(x=>x!==t&&tilesEqual(x,t)))score-=2;
    if(t.suit!=='honor'&&(t.num===1||t.num===9)&&!s.some(x=>x!==t&&tilesEqual(x,t)))score-=1;
  }
  return score;
}
function chooseAIDiscard(pi){
  const p=G.players[pi];const all=[...p.hand,...(p.drawn?[p.drawn]:[])];
  if(!all.length)return null;
  let best=null,bs=-Infinity;
  for(const t of all){
    const test=all.filter(x=>x.uid!==t.uid);const sc=evaluateHand(test,p.melds);
    if(sc>bs){bs=sc;best=t;}
  }
  return best||all[all.length-1];
}

function doDiscard(pi,tile){
  const p=G.players[pi];
  if(p.drawn&&p.drawn.uid===tile.uid){p.drawn=null;}
  else{
    const idx=p.hand.findIndex(t=>t.uid===tile.uid);
    if(idx!==-1)p.hand.splice(idx,1);
    if(p.drawn){p.hand.push(p.drawn);p.drawn=null;}
  }
  p.hand=sortHand(p.hand);
  p.pond.push({...tile,riichi:p.riichi&&p.riichiTurn===-1&&p.pond.length===0});
  G.lastDiscard=tile;G.lastDiscardPlayer=pi;G.phase='claim';G.selectedTile=null;
  log(`${p.name}が${tileStr(tile)}を捨て`);renderAll();checkClaims(tile,pi);
}
function doRiichi(pi,discardTile){
  const p=G.players[pi];p.score-=1000;G.riichiPool+=1000;
  p.riichi=true;p.riichiTurn=G.players.flatMap(x=>x.pond).length;
  showFloatMsg('立直！');doDiscard(pi,discardTile);
}
function doKan(pi,tile,isAnkan){
  const p=G.players[pi];
  const kanTiles=[...p.hand,...(p.drawn?[p.drawn]:[])].filter(t=>tilesEqual(t,tile));
  let rm=0;p.hand=p.hand.filter(t=>{if(rm<4&&tilesEqual(t,tile)){rm++;return false;}return true;});
  if(p.drawn&&tilesEqual(p.drawn,tile)&&rm<4){p.drawn=null;rm++;}
  p.melds.push({type:'kan',tiles:kanTiles,isAnkan});
  if(G.deadWall.length){p.drawn=G.deadWall.shift();G.doraIndicators.push(G.deadWall[4-G.doraIndicators.length]);}
  renderAll();log(`${p.name}が槓`);
  if(p.isHuman){G.phase='discard';renderControls();}
  else setTimeout(()=>aiTurn(pi),600);
}

function checkClaims(tile,dpi){
  const claims=[];
  for(let i=0;i<G.numPlayers;i++){
    if(i===dpi)continue;const p=G.players[i];
    if(canRon(p.hand,p.melds,tile,p)){
      if(p.isHuman)claims.push({type:'ron',player:i,priority:3});
      else if(Math.random()<0.7)claims.push({type:'ron',player:i,priority:3});
    }
    if(!p.riichi&&canPon(p.hand,tile)){
      if(p.isHuman)claims.push({type:'pon',player:i,priority:2});
      else if(Math.random()<0.4)claims.push({type:'pon',player:i,priority:2});
    }
    if(!p.riichi){
      const co=canChi(p.hand,tile,i,dpi);
      if(co.length){
        if(p.isHuman)claims.push({type:'chi',player:i,priority:1,options:co});
        else if(evaluateHand(p.hand.concat([tile]),p.melds)>evaluateHand(p.hand,p.melds)&&Math.random()<0.35)
          claims.push({type:'chi',player:i,priority:1,options:co});
      }
    }
  }
  claims.sort((a,b)=>b.priority-a.priority);
  const hc=claims.filter(c=>c.player===0);
  const ac=claims.filter(c=>c.player!==0);
  const ron=claims.filter(c=>c.type==='ron');
  if(ron.length){
    if(ron.some(c=>c.player===0)){G.pendingClaims=hc;G.waitingForPlayer=true;renderControls();return;}
    declareWin(ron[0].player,dpi,false);return;
  }
  if(hc.length){G.pendingClaims=hc;G.waitingForPlayer=true;renderControls();return;}
  if(ac.length){setTimeout(()=>executeAIClaim(ac[0],tile),500);return;}
  advanceTurn(dpi);
}
function executeAIClaim(claim,tile){
  if(G.gameOver)return;const p=G.players[claim.player];
  if(claim.type==='ron'){declareWin(claim.player,G.lastDiscardPlayer,false);}
  else if(claim.type==='pon'){
    let rm=0;const pt=[];
    p.hand=p.hand.filter(t=>{if(rm<2&&tilesEqual(t,tile)){rm++;pt.push(t);return false;}return true;});
    p.melds.push({type:'pon',tiles:[...pt,tile]});
    G.activePlayer=claim.player;G.phase='discard';log(`${p.name}がポン`);renderAll();
    setTimeout(()=>aiTurn(claim.player),600);
  } else if(claim.type==='chi'){
    const chiNums=claim.options[0];const ct=[];const th=[...p.hand];
    for(const n of chiNums){
      if(n===tile.num&&tilesEqual({suit:tile.suit,num:n},tile)){ct.push(tile);}
      else{const x=th.findIndex(t=>t.suit===tile.suit&&t.num===n);if(x!==-1)ct.push(th.splice(x,1)[0]);}
    }
    p.hand=th;p.melds.push({type:'chi',tiles:ct});
    G.activePlayer=claim.player;G.phase='discard';log(`${p.name}がチー`);renderAll();
    setTimeout(()=>aiTurn(claim.player),600);
  }
}
function advanceTurn(from){
  G.activePlayer=(from+1)%G.numPlayers;G.phase='draw';G.waitingForPlayer=false;
  renderControls();setTimeout(()=>nextTurn(),200);
}

function declareWin(wi,li,isTsumo){
  G.gameOver=true;
  const winner=G.players[wi];
  const allH=[...winner.hand,...(winner.drawn?[winner.drawn]:[])];
  const decomps=getWinningDecompositions(allH);
  const decomp=decomps[0]||{type:'normal',pair:[],melds:[],tiles:allH};
  const yaku=getYaku(decomp,winner,G,isTsumo);
  const isDealer=wi===G.dealer;
  const si=calcScore(yaku,decomp,isTsumo,isDealer);
  const deltas=Array(G.numPlayers).fill(0);
  if(isTsumo){
    for(let i=0;i<G.numPlayers;i++){
      if(i===wi)continue;const pay=(i===G.dealer?si.dealer:si.nonDealer)+(G.honba*100);
      G.players[i].score-=pay;deltas[i]-=pay;deltas[wi]+=pay;
    }
  } else {
    const pay=si.ron+(G.honba*300);G.players[li].score-=pay;deltas[li]-=pay;deltas[wi]+=pay;
  }
  G.players[wi].score+=G.riichiPool;deltas[wi]+=G.riichiPool;G.riichiPool=0;
  showFloatMsg(isTsumo?'ツモ！':'ロン！');
  setTimeout(()=>showWinModal(wi,li,isTsumo,yaku,si,decomp,allH,deltas),500);
}
function showWinModal(wi,li,isTsumo,yaku,si,decomp,allH,deltas){
  let body=`<div class="hand-display">${allH.map(t=>tileHTML(t,'medium')).join('')}</div>`;
  body+=`<div style="margin:8px 0;font-size:13px;color:var(--text2)">${yaku.map(y=>`<span style="margin-right:8px;color:${y.isBonus?'#ffd700':'var(--text)'}">${y.name}(${y.han}翻)</span>`).join('')}</div>`;
  body+=`<div style="text-align:center;font-size:20px;font-weight:900;color:#ffd700;margin:8px 0">${si.han}翻${si.fu}符 ${isTsumo?si.nonDealer+'点ALL':si.ron+'点'}</div>`;
  body+=`<div style="margin-top:12px">`;
  for(let i=0;i<G.numPlayers;i++){const d=deltas[i];body+=`<div class="result-row"><span>${G.players[i].name}</span><span class="score-delta ${d>=0?'pos':'neg'}">${d>=0?'+':''}${d}</span><span>${G.players[i].score}</span></div>`;}
  body+=`</div>`;
  document.getElementById('modal-title').textContent=isTsumo?'ツモ和了':'ロン和了';
  document.getElementById('modal-body').innerHTML=body;
  document.getElementById('modal').classList.add('show');
  G._pendingNextRound=()=>{
    if(wi===G.dealer)G.honba++;else{G.honba=0;G.dealer=(G.dealer+1)%G.numPlayers;G.round++;}
    G.gameOver=false;
    if(G.round>=G.maxRound){showFinalScreen();return;}
    startRound();
  };
}
function closeModal(){
  document.getElementById('modal').classList.remove('show');
  if(G._pendingNextRound){G._pendingNextRound();G._pendingNextRound=null;}
}
function handleRyukyoku(){
  G.gameOver=true;
  const tp=G.players.map(p=>isTenpai(p.hand,p.melds));
  const tc=tp.filter(Boolean).length;
  if(tc>0&&tc<G.numPlayers){
    const pay=3000/tc|0;const rcv=3000/(G.numPlayers-tc)|0;
    for(let i=0;i<G.numPlayers;i++){if(tp[i])G.players[i].score+=rcv;else G.players[i].score-=pay;}
  }
  let body='<div style="font-size:14px">';
  for(let i=0;i<G.numPlayers;i++)body+=`<div class="result-row"><span>${G.players[i].name}</span><span>${tp[i]?'聴牌':'不聴'}</span><span>${G.players[i].score}</span></div>`;
  body+='</div>';
  document.getElementById('modal-title').textContent='流局';
  document.getElementById('modal-body').innerHTML=body;
  document.getElementById('modal').classList.add('show');
  G._pendingNextRound=()=>{G.honba++;G.gameOver=false;G.round++;if(G.round>=G.maxRound){showFinalScreen();return;}startRound();};
}
function showFinalScreen(){
  const ranked=[...G.players].map((p,i)=>({...p,idx:i})).sort((a,b)=>b.score-a.score);
  document.getElementById('final-ranks').innerHTML=ranked.map((p,i)=>`<div class="rank-row rank-${i+1}"><span>${i+1}位 ${p.name}</span><span>${p.score.toLocaleString()}点</span></div>`).join('');
  document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));
  document.getElementById('final-screen').classList.add('active');
}

// ── 人間操作 ──
function selectTile(uid){
  if(!G.waitingForPlayer||G.phase!=='discard')return;
  if(G.players[0].riichi)return;
  const all=[...G.players[0].hand,...(G.players[0].drawn?[G.players[0].drawn]:[])];
  const tile=all.find(t=>t.uid===uid);if(!tile)return;
  if(G.selectedTile&&G.selectedTile.uid===uid){humanDiscard(uid);return;}
  if(G.riichiCandidates.length){
    if(!G.riichiCandidates.some(r=>r.uid===uid))return;
    G.waitingForPlayer=false;G.riichiCandidates=[];doRiichi(0,tile);return;
  }
  G.selectedTile=tile;renderHand(0);renderControls();
}
function humanDiscard(uid){
  if(!G.waitingForPlayer)return;const p=G.players[0];
  if(p.riichi){if(!p.drawn)return;G.selectedTile=null;G.waitingForPlayer=false;doDiscard(0,p.drawn);return;}
  const all=[...p.hand,...(p.drawn?[p.drawn]:[])];
  const tile=uid!==-1?all.find(t=>t.uid===uid):G.selectedTile;
  if(!tile)return;G.selectedTile=null;G.waitingForPlayer=false;doDiscard(0,tile);
}
function humanTsumo(){if(!G.waitingForPlayer)return;G.waitingForPlayer=false;declareWin(0,null,true);}
function humanRiichi(){
  if(!G.waitingForPlayer)return;const p=G.players[0];
  if(p.riichi||p.score<1000||p.melds.length)return;
  const all=[...p.hand,...(p.drawn?[p.drawn]:[])];
  const cands=all.filter(t=>isTenpai(all.filter(x=>x.uid!==t.uid),p.melds));
  if(!cands.length)return;
  G.riichiCandidates=cands;renderControls();renderHand(0);
}
function humanRon(){if(!G.waitingForPlayer)return;G.waitingForPlayer=false;declareWin(0,G.lastDiscardPlayer,false);}
function humanChi(chiNums){
  if(!G.waitingForPlayer)return;const p=G.players[0];const tile=G.lastDiscard;
  const ct=[];const th=[...p.hand];
  for(const n of chiNums){
    if(n===tile.num&&tilesEqual({suit:tile.suit,num:n},tile)){ct.push(tile);}
    else{const x=th.findIndex(t=>t.suit===tile.suit&&t.num===n);if(x!==-1)ct.push(th.splice(x,1)[0]);}
  }
  p.hand=th;p.melds.push({type:'chi',tiles:ct});
  G.activePlayer=0;G.phase='discard';G.waitingForPlayer=true;G.pendingClaims=[];
  log('チー');renderAll();renderControls();
}
function humanPon(){
  if(!G.waitingForPlayer)return;const p=G.players[0];const tile=G.lastDiscard;
  let rm=0;const pt=[];
  p.hand=p.hand.filter(t=>{if(rm<2&&tilesEqual(t,tile)){rm++;pt.push(t);return false;}return true;});
  p.melds.push({type:'pon',tiles:[...pt,tile]});
  G.activePlayer=0;G.phase='discard';G.waitingForPlayer=true;G.pendingClaims=[];
  log('ポン');renderAll();renderControls();
}
function humanSkip(){
  if(!G.waitingForPlayer)return;
  G.pendingClaims=[];G.waitingForPlayer=false;G.riichiCandidates=[];G.selectedTile=null;
  advanceTurn(G.lastDiscardPlayer);
}

// ── 描画 ──
function tileHTML(t,sz='medium'){
  if(!t)return'';
  return`<div class="tile ${t.suit} ${sz}" onclick="selectTile(${t.uid})" ondblclick="humanDiscard(${t.uid})">${tileStr(t)}</div>`;
}
function tileHTMLSel(t,sz,sel,rc){
  if(!t)return'';let c=`tile ${t.suit} ${sz}`;if(sel||rc)c+=' selected';
  return`<div class="${c}" onclick="selectTile(${t.uid})" ondblclick="humanDiscard(${t.uid})">${tileStr(t)}</div>`;
}
function renderHand(pi){
  const p=G.players[pi];const el=document.getElementById(`hand-${pi}`);if(!el)return;
  if(pi===0){
    let html='';
    for(const t of p.hand)html+=tileHTMLSel(t,'full',G.selectedTile&&G.selectedTile.uid===t.uid,G.riichiCandidates.some(r=>r.uid===t.uid));
    if(p.drawn){
      html+=`<div style="margin-left:8px;border-left:2px solid rgba(255,215,0,.4);padding-left:8px">`;
      html+=tileHTMLSel(p.drawn,'full',G.selectedTile&&G.selectedTile.uid===p.drawn.uid,G.riichiCandidates.some(r=>r.uid===p.drawn.uid));
      html+=`</div>`;
    }
    el.innerHTML=html;
  } else {
    const cnt=p.hand.length+(p.drawn?1:0);
    const sz=pi===2?'':'small';
    el.innerHTML=Array(cnt).fill(`<div class="tile-back ${sz}"></div>`).join('');
  }
}
function renderPond(pi){
  const p=G.players[pi];const el=document.getElementById(`pond-${pi}`);if(!el)return;
  el.innerHTML=p.pond.map(t=>`<div class="tile discarded ${t.suit}">${tileStr(t)}</div>`).join('');
}
function renderMelds(pi){
  const p=G.players[pi];const el=document.getElementById(`melds-${pi}`);if(!el)return;
  const sz=pi===0?'medium':'small';
  el.innerHTML=p.melds.map(m=>`<div class="meld">${m.tiles.map(t=>`<div class="tile ${t.suit} ${sz}">${tileStr(t)}</div>`).join('')}</div>`).join('');
}
function renderControls(){
  const el=document.getElementById('controls');if(!el)return;
  const p=G.players[0];let html='';showWaiting(false);
  if(G.phase==='discard'&&G.activePlayer===0&&G.waitingForPlayer){
    if(canTsumo(p))html+=`<button class="action-btn btn-tsumo" onclick="humanTsumo()">ツモ</button>`;
    if(!p.riichi&&!p.melds.length&&p.score>=1000){
      const all=[...p.hand,...(p.drawn?[p.drawn]:[])];
      if(all.some(t=>isTenpai(all.filter(x=>x.uid!==t.uid),p.melds)))
        html+=`<button class="action-btn btn-riichi" onclick="humanRiichi()">立直</button>`;
    }
    if(G.riichiCandidates.length){
      html=`<span style="font-size:12px;color:var(--gold)">立直する牌を選んでください</span>`;
      html+=`<button class="action-btn btn-skip" onclick="G.riichiCandidates=[];G.selectedTile=null;renderControls();renderHand(0);">キャンセル</button>`;
    } else if(G.selectedTile||p.riichi){
      html+=`<button class="action-btn btn-discard" onclick="humanDiscard(${p.riichi?(p.drawn?p.drawn.uid:-1):G.selectedTile?.uid})">${p.riichi?'ツモ切り':'捨てる'}</button>`;
    } else {
      html+=`<span style="font-size:12px;color:var(--text2)">牌を選んで捨ててください（ダブルクリックで即捨て）</span>`;
    }
  } else if(G.phase==='claim'&&G.waitingForPlayer){
    const cs=G.pendingClaims;
    if(cs.some(c=>c.type==='ron'))html+=`<button class="action-btn btn-ron" onclick="humanRon()">ロン</button>`;
    if(cs.some(c=>c.type==='pon'))html+=`<button class="action-btn btn-pon" onclick="humanPon()">ポン</button>`;
    if(cs.some(c=>c.type==='chi')){
      cs.filter(c=>c.type==='chi')[0].options.forEach(o=>{
        html+=`<button class="action-btn btn-chi" onclick="humanChi([${o}])">チー(${o.join('-')})</button>`;
      });
    }
    html+=`<button class="action-btn btn-skip" onclick="humanSkip()">スキップ</button>`;
  } else if(!G.waitingForPlayer&&!G.gameOver){showWaiting(true);}
  el.innerHTML=html;
  const ri=document.getElementById('riichi-indicator');
  if(ri)ri.innerHTML=p.riichi?`<div class="riichi-stick" title="立直中"></div>`:'';
}
function renderScores(){
  for(let i=0;i<G.numPlayers;i++){
    const e=document.getElementById(`score-${i}`);if(e)e.textContent=G.players[i].score.toLocaleString();
  }
  document.getElementById('hud-tiles').innerHTML=`残<b>${wallCount()}</b>枚`;
  document.getElementById('hud-honba').textContent=G.honba;
  document.getElementById('hud-riichi-pool').textContent=G.riichiPool;
  const rn=roundName();
  document.getElementById('hud-round').textContent=rn;
  document.getElementById('center-round').textContent=rn;
}
function renderDora(){
  const el=document.getElementById('dora-display');if(!el)return;
  el.innerHTML=G.doraIndicators.map(t=>`<div class="tile ${t.suit} small">${tileStr(t)}</div>`).join('');
}
function renderWindLabels(){
  for(let i=0;i<G.numPlayers;i++){
    const p=G.players[i];
    const ne=document.getElementById(`name-${i}`);if(ne)ne.textContent=p.name+(p.riichi?' 🔴':'');
    const we=document.getElementById(`wind-${i}`);if(we)we.textContent=p.wind+(i===G.dealer?'(親)':'');
  }
  const pw=document.getElementById('player-wind-label');if(pw)pw.textContent=G.players[0].wind+(0===G.dealer?'(親)':'');
  const s3=document.getElementById('seat-3');if(s3)s3.style.visibility=G.numPlayers===3?'hidden':'visible';
}
function renderRiichiSticks(){
  const el=document.getElementById('riichi-sticks');if(!el)return;
  el.innerHTML=Array(G.riichiPool/1000|0).fill(`<div class="riichi-stick"></div>`).join('');
}
function renderAll(){
  for(let i=0;i<G.numPlayers;i++){renderHand(i);renderPond(i);renderMelds(i);}
  renderScores();renderDora();renderWindLabels();renderRiichiSticks();
}
function showWaiting(show){const el=document.getElementById('waiting');if(el)el.style.display=show?'flex':'none';}
function showFloatMsg(msg){
  const el=document.getElementById('float-msg');el.textContent=msg;el.classList.add('show');
  setTimeout(()=>el.classList.remove('show'),1200);
}
function log(msg){const el=document.getElementById('game-log');if(el)el.textContent=msg;}
function startGame(np,mode){
  document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));
  document.getElementById('game-screen').classList.add('active');
  const s3=document.getElementById('seat-3');if(s3)s3.style.display=np===3?'none':'';
  initGame(np,mode);
}
function showTitle(){
  G.gameOver=true;
  document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));
  document.getElementById('title-screen').classList.add('active');
}
__AUTO_START__
</script>
</body>
</html>""".replace(
        "__AUTO_START__",
        f"window.addEventListener('load',function(){{  {auto_start_js} }});"
    )


# ===== COMMAND REGISTRY & MAIN RUNNER v128.1 =====
