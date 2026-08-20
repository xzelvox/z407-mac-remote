"""ポップオーバーに表示する Aurora パネル(緑テーマ / v2)の HTML/CSS/JS。

ユーザーのデザイン `Speaker Control.dc.html`(案A "Aurora" 緑版)の見た目を、
DCLogic/support.js を使わない静的 HTML + 自前 JS に移植したもの。
- Python→JS: `applyState(<json>)`(WKWebView.evaluateJavaScript)
- JS→Python: `window.webkit.messageHandlers.bridge.postMessage({action, value})`
- Spotify 未接続(未起動)時は再生部を隠してプレースホルダを表示。
- 元デザインにあった Quit はメニューバーアイコンの右クリックメニューで提供する。
"""

HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  *{ box-sizing:border-box; }
  html,body{ margin:0; padding:0; height:100%; overflow:hidden; }
  body{ font-family:-apple-system,sans-serif; color:#E8EFE7; background:linear-gradient(165deg,#191d1a 0%,#13160f 55%,#0d0f0c 100%); }
  @keyframes ringspin{ to{ transform:rotate(360deg); } }
  button{ font-family:-apple-system,sans-serif; }
</style>
</head>
<body>
  <div id="card" style="position:relative; padding:26px;">

    <!-- header -->
    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:22px;">
      <div style="display:flex; align-items:center; gap:12px;">
        <div style="width:42px; height:42px; border-radius:12px; background:radial-gradient(circle at 35% 30%,#39403a,#181c18); border:1px solid rgba(107,203,139,.25); display:flex; align-items:center; justify-content:center;">
          <div style="width:18px; height:18px; border-radius:50%; border:2px solid #6BCB8B; box-shadow:0 0 12px rgba(107,203,139,.5);"></div>
        </div>
        <div>
          <div style="font-size:15px; font-weight:700;">Logitech Z407</div>
          <div style="display:flex; align-items:center; gap:6px; margin-top:3px;">
            <span id="dot" style="width:7px; height:7px; border-radius:50%; background:#6b6b6b;"></span>
            <span id="status" style="font-size:11px; font-weight:600; letter-spacing:.04em; color:#94a08f;">Disconnected</span>
          </div>
        </div>
      </div>
      <div style="display:flex; align-items:center; gap:8px;">
        <button id="spChip" onclick="send('spotifyOpen')" title="Spotify を開く" style="display:flex; align-items:center; gap:7px; padding:6px 11px; border-radius:20px; border:1px solid rgba(255,255,255,.08); background:rgba(255,255,255,.03); cursor:pointer;">
          <span id="spChipLabel" style="font-size:11px; font-weight:700; letter-spacing:.03em; color:#7a857a;">未接続</span>
        </button>
        <button id="langToggle" onclick="toggleLang()" title="Switch language / 言語切替" style="padding:6px 9px; border-radius:9px; border:1px solid rgba(255,255,255,.12); background:rgba(255,255,255,.05); color:#7FE0A3; cursor:pointer; font-size:11px; font-weight:800; letter-spacing:.03em;">EN</button>
        <button onclick="send('quit')" title="Quit" style="width:30px; height:30px; border-radius:9px; border:1px solid rgba(255,255,255,.08); background:rgba(255,255,255,.03); color:#8a857d; cursor:pointer; display:flex; align-items:center; justify-content:center; flex:none;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M12 4v8"/><path d="M6.5 7a8 8 0 1 0 11 0"/></svg>
        </button>
      </div>
    </div>

    <div id="msg" style="font-size:11px; text-align:center; color:#7FE0A3; min-height:0;"></div>

    <!-- controls -->
    <div id="controls" style="opacity:1; pointer-events:auto; transition:opacity .3s;">

      <!-- ===== playback (Spotify 起動時のみ) ===== -->
      <div id="playback" style="display:none;">
        <div style="display:flex; align-items:center; gap:14px; margin-bottom:16px;">
          <div id="disc" style="width:60px; height:60px; flex:none; border-radius:50%; background:conic-gradient(from 210deg,#6BCB8B,#2f7d4e,#1f2a22,#6BCB8B); box-shadow:0 6px 16px -6px rgba(107,203,139,.6); position:relative; animation:ringspin 6s linear infinite; animation-play-state:paused;">
            <div style="position:absolute; inset:0; border-radius:50%; background:radial-gradient(circle at 50% 50%,transparent 24%,rgba(0,0,0,.5) 26%);"></div>
            <div style="position:absolute; left:50%; top:50%; transform:translate(-50%,-50%); width:12px; height:12px; border-radius:50%; background:#11140f; border:1px solid rgba(255,255,255,.15);"></div>
          </div>
          <div style="flex:1; min-width:0;">
            <div id="npTitle" style="font-size:14px; font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">—</div>
            <div id="npArtist" style="font-size:12px; color:#94a08f; margin-top:3px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">Spotify</div>
          </div>
        </div>

        <div style="margin-bottom:18px;">
          <div style="position:relative; height:4px; border-radius:2px; background:rgba(255,255,255,.1);">
            <div id="progFill" style="position:absolute; left:0; top:0; height:4px; border-radius:2px; width:0%; background:linear-gradient(90deg,#2F9E5F,#7FE0A3);"></div>
          </div>
          <div style="display:flex; justify-content:space-between; margin-top:7px;">
            <span id="elapsed" style="font-family:ui-monospace,monospace; font-size:11px; color:#94a08f;">0:00</span>
            <span id="total" style="font-family:ui-monospace,monospace; font-size:11px; color:#94a08f;">0:00</span>
          </div>
        </div>

        <div style="display:flex; align-items:center; justify-content:center; gap:26px; margin-bottom:22px;">
          <button onclick="send('prev')" title="Previous" style="width:44px; height:44px; border-radius:50%; border:none; cursor:pointer; background:rgba(255,255,255,.05); color:#E8EFE7; display:flex; align-items:center; justify-content:center;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M6 6h2v12H6z"/><path d="M20 6v12L9.5 12z"/></svg>
          </button>
          <button onclick="send('play')" title="Play / Pause" style="width:58px; height:58px; border-radius:50%; border:none; cursor:pointer; background:linear-gradient(150deg,#7FE0A3,#2F9E5F); box-shadow:0 8px 20px -5px rgba(107,203,139,.65); color:#08160d; display:flex; align-items:center; justify-content:center;">
            <span id="playIcon"><svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg></span>
          </button>
          <button onclick="send('next')" title="Next" style="width:44px; height:44px; border-radius:50%; border:none; cursor:pointer; background:rgba(255,255,255,.05); color:#E8EFE7; display:flex; align-items:center; justify-content:center;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M16 6h2v12h-2z"/><path d="M4 6v12L14.5 12z"/></svg>
          </button>
        </div>
      </div>

      <!-- ===== placeholder (Spotify 未起動) ===== -->
      <div id="spPlaceholder" style="display:none; flex-direction:column; align-items:center; gap:12px; padding:26px 0 30px; margin-bottom:6px;">
        <div id="spPhText" style="font-size:13px; font-weight:600; color:#8a9686;" data-i18n="spNotConnected">Spotifyが接続されていません</div>
        <button onclick="send('spotifyOpen')" style="padding:9px 20px; border-radius:11px; border:1px solid rgba(107,203,139,.4); cursor:pointer; font-size:12px; font-weight:800; letter-spacing:.04em; color:#7FE0A3; background:rgba(107,203,139,.1);" data-i18n="spConnect">Spotifyに接続</button>
      </div>

      <!-- audio: volume + bass knobs -->
      <div style="margin-bottom:20px;">
        <div style="display:flex; gap:14px;">

          <!-- volume knob (left, always enabled) -->
          <div style="flex:1; display:flex; flex-direction:column; align-items:center; gap:6px;">
            <div style="display:flex; align-items:baseline; gap:6px;">
              <span style="font-size:12px; font-weight:700; letter-spacing:.08em; color:#94a08f;" data-i18n="volume">Volume</span>
              <span id="volVal" style="font-size:16px; font-weight:700; color:#4ade80;">50</span>
            </div>
            <div style="display:flex; align-items:center; gap:6px;">
              <button id="volDec" style="width:30px;height:30px;border-radius:10px;background:#111d17;border:1px solid #1d2f25;color:#cfe8d9;font-size:17px;line-height:1;display:flex;align-items:center;justify-content:center;cursor:pointer;user-select:none;">-</button>
              <div id="volOuter" style="width:72px;height:72px;flex:none;position:relative;border-radius:50%;background:radial-gradient(circle at 50% 35%,#1a2c21,#0b140f 72%);border:1px solid #24382c;display:flex;align-items:center;justify-content:center;">
                <div id="volRing" style="position:absolute;inset:3px;border-radius:50%;background:conic-gradient(from 225deg, rgba(74,222,128,.55) 0turn, rgba(74,222,128,.55) 0turn, rgba(255,255,255,.05) 0turn, rgba(255,255,255,.05) .75turn, transparent .75turn);-webkit-mask:radial-gradient(circle,transparent 30px,#000 31px);mask:radial-gradient(circle,transparent 30px,#000 31px);"></div>
                <div id="volDial" style="width:50px;height:50px;border-radius:50%;background:linear-gradient(180deg,#16261d,#0d1913);border:1px solid #2b4536;transform:rotate(-135deg);display:flex;justify-content:center;padding-top:6px;">
                  <div style="width:3px;height:15px;border-radius:2px;background:#5de394;box-shadow:0 0 6px rgba(74,222,128,.75);"></div>
                </div>
              </div>
              <button id="volInc" style="width:30px;height:30px;border-radius:10px;background:#111d17;border:1px solid #1d2f25;color:#cfe8d9;font-size:17px;line-height:1;display:flex;align-items:center;justify-content:center;cursor:pointer;user-select:none;">+</button>
            </div>
          </div>

          <!-- bass knob (right, gated by connection) -->
          <div id="bassCtrl" style="flex:1; display:flex; flex-direction:column; align-items:center; gap:6px; opacity:.35;">
            <div style="display:flex; align-items:baseline; gap:6px;">
              <span style="font-size:12px; font-weight:700; letter-spacing:.08em; color:#94a08f;" data-i18n="bass">Bass</span>
              <span id="bassVal" style="font-size:16px; font-weight:700; color:#d6dedb;">0</span>
            </div>
            <div style="display:flex; align-items:center; gap:6px;">
              <button id="bassDec" style="width:30px;height:30px;border-radius:10px;background:#111d17;border:1px solid #1d2f25;color:#cfe8d9;font-size:17px;line-height:1;display:flex;align-items:center;justify-content:center;cursor:pointer;user-select:none;">-</button>
              <div id="bassOuter" style="width:72px;height:72px;flex:none;position:relative;border-radius:50%;background:radial-gradient(circle at 50% 35%,#1a2c21,#0b140f 72%);border:1px solid #24382c;display:flex;align-items:center;justify-content:center;">
                <div id="bassRing" style="position:absolute;inset:3px;border-radius:50%;background:conic-gradient(from 225deg, rgba(203,213,205,.55) 0turn, rgba(203,213,205,.55) 0turn, rgba(255,255,255,.05) 0turn, rgba(255,255,255,.05) .75turn, transparent .75turn);-webkit-mask:radial-gradient(circle,transparent 30px,#000 31px);mask:radial-gradient(circle,transparent 30px,#000 31px);"></div>
                <div id="bassDial" style="width:50px;height:50px;border-radius:50%;background:linear-gradient(180deg,#16261d,#0d1913);border:1px solid #2b4536;transform:rotate(-135deg);display:flex;justify-content:center;padding-top:6px;">
                  <div style="width:3px;height:15px;border-radius:2px;background:#d6dedb;box-shadow:0 0 6px rgba(203,213,205,.75);"></div>
                </div>
              </div>
              <button id="bassInc" style="width:30px;height:30px;border-radius:10px;background:#111d17;border:1px solid #1d2f25;color:#cfe8d9;font-size:17px;line-height:1;display:flex;align-items:center;justify-content:center;cursor:pointer;user-select:none;">+</button>
            </div>
          </div>

        </div>
      </div>

      <!-- BLE 依存コントロール(接続状態で有効化) -->
      <div id="bleControls" style="opacity:.35; pointer-events:none; transition:opacity .3s;">

      <!-- input segmented -->
      <div style="margin-bottom:18px;">
        <div style="font-size:11px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:#94a08f; margin-bottom:10px;" data-i18n="input">Input</div>
        <div style="display:flex; gap:6px; padding:4px; border-radius:12px; background:rgba(0,0,0,.3);">
          <button id="inBT"  onclick="send('input','BT')"  style="flex:1; border:none; cursor:pointer; padding:9px 0; border-radius:9px; font-size:12px; font-weight:700; transition:all .2s; background:transparent; color:#94a08f;">BT</button>
          <button id="inAUX" onclick="send('input','AUX')" style="flex:1; border:none; cursor:pointer; padding:9px 0; border-radius:9px; font-size:12px; font-weight:700; transition:all .2s; background:transparent; color:#94a08f;">AUX</button>
          <button id="inUSB" onclick="send('input','USB')" style="flex:1; border:none; cursor:pointer; padding:9px 0; border-radius:9px; font-size:12px; font-weight:700; transition:all .2s; background:transparent; color:#94a08f;">USB</button>
        </div>
      </div>

      <!-- bluetooth pairing -->
      <div style="display:flex; align-items:center; justify-content:space-between; padding:13px 14px; border-radius:14px; background:rgba(255,255,255,.035);">
        <div style="display:flex; align-items:center; gap:10px;">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#8a857d" stroke-width="2" stroke-linejoin="round"><path d="M7 7l10 10-5 4V3l5 4L7 17"/></svg>
          <span style="font-size:13px; font-weight:600;" data-i18n="btPairing">Bluetooth Pairing</span>
        </div>
        <button id="btToggle" onclick="send('pair')" style="width:46px; height:26px; border-radius:13px; border:none; cursor:pointer; padding:3px; transition:background .25s; background:rgba(255,255,255,.12); display:flex; justify-content:flex-start;">
          <span style="width:20px; height:20px; border-radius:50%; background:#fff; box-shadow:0 2px 5px rgba(0,0,0,.4); transition:all .25s;"></span>
        </button>
      </div>

      <div style="margin-top:14px; text-align:center;">
        <button id="resetBtn" onclick="onReset()" style="border:none; background:none; cursor:pointer; font-size:11px; letter-spacing:.03em; color:#9a6b6b;" data-i18n="factoryReset">Factory Reset</button>
      </div>
      </div><!-- /bleControls -->
    </div>

    <!-- connect overlay -->
    <div id="connectArea" style="position:absolute; left:26px; right:26px; bottom:22px;">
      <button id="connectBtn" onclick="send('connect')" style="width:100%; padding:13px; border-radius:13px; border:none; cursor:pointer; font-size:13px; font-weight:800; letter-spacing:.04em; color:#08160d; background:linear-gradient(150deg,#7FE0A3,#2F9E5F); box-shadow:0 8px 20px -6px rgba(107,203,139,.6);" data-i18n="connect">CONNECT</button>
      <div style="display:flex; gap:8px; margin-top:9px;">
        <button id="pairBtn2" onclick="onPair2()" style="flex:1; padding:9px 0; border-radius:10px; border:1px solid rgba(127,224,163,.4); background:rgba(127,224,163,.08); cursor:pointer; font-size:11px; font-weight:700; color:#7FE0A3;" data-i18n="pairing">Pairing</button>
        <button id="resetBtn2" onclick="onReset2()" style="flex:1; padding:9px 0; border-radius:10px; border:1px solid rgba(224,135,107,.35); background:rgba(224,135,107,.06); cursor:pointer; font-size:11px; font-weight:700; color:#cf8a78;" data-i18n="factoryReset2">Factory Reset</button>
      </div>
    </div>
  </div>

<script>
  function send(action, value){
    try{ window.webkit.messageHandlers.bridge.postMessage({action:action, value:(value===undefined?null:value)}); }
    catch(e){}
  }
  function $(id){ return document.getElementById(id); }

  // ---- i18n ----
  var I18N = {
    ja: {
      spNotConnected:'Spotifyが接続されていません',
      spConnect:'Spotifyに接続',
      volume:'音量',
      bass:'低音',
      input:'入力',
      btPairing:'Bluetooth ペアリング',
      factoryReset:'ファクトリーリセット',
      factoryReset2:'ファクトリーリセット',
      connect:'接続',
      pairing:'ペアリング',
      statusConnecting:'接続中…',
      statusConnected:'接続済み',
      statusDisconnected:'未接続',
      connectBtnConnecting:'再接続中…(タップで中止)',
      spNotConnectedLabel:'未接続',
      spNotFound:'Spotify が見つかりません',
      resetConfirm:'⚠︎ もう一度タップで初期化',
      resetConfirm2:'⚠ もう一度タップ',
    },
    en: {
      spNotConnected:'Spotify is not connected',
      spConnect:'Connect Spotify',
      volume:'Volume',
      bass:'Bass',
      input:'Input',
      btPairing:'Bluetooth Pairing',
      factoryReset:'Factory Reset',
      factoryReset2:'Factory Reset',
      connect:'CONNECT',
      pairing:'Pairing',
      statusConnecting:'Connecting…',
      statusConnected:'Connected',
      statusDisconnected:'Disconnected',
      connectBtnConnecting:'Reconnecting… (tap to cancel)',
      spNotConnectedLabel:'Not connected',
      spNotFound:'Spotify not found',
      resetConfirm:'⚠ Tap again to reset',
      resetConfirm2:'⚠ Tap again',
    }
  };
  var lang = 'ja';
  function t(key){ return (I18N[lang] && I18N[lang][key]) || (I18N.ja[key] || key); }
  function applyLang(){
    var el = document.querySelectorAll('[data-i18n]');
    for(var i=0;i<el.length;i++){ var k=el[i].getAttribute('data-i18n'); el[i].textContent=t(k); }
    $('langToggle').textContent = (lang==='ja') ? 'EN' : 'JA';
    $('langToggle').title = (lang==='ja') ? 'Switch to English' : 'Switch to Japanese';
  }
  function toggleLang(){ lang = (lang==='ja') ? 'en' : 'ja'; applyLang(); send('setLang', lang); }
  window.applyLang = applyLang;

  // Factory Reset(2タップ確認)
  var resetArmed=false, resetTimer=null;
  function resetCancel(){
    resetArmed=false; if(resetTimer){ clearTimeout(resetTimer); resetTimer=null; }
    var b=$('resetBtn'); if(b){ b.textContent=t('factoryReset'); b.style.color='#9a6b6b'; }
  }
  function onReset(){
    if($('bleControls').style.pointerEvents==='none') return;
    if(!resetArmed){
      resetArmed=true;
      $('resetBtn').textContent=t('resetConfirm');
      $('resetBtn').style.color='#E0876B';
      resetTimer=setTimeout(resetCancel, 4000);
    } else {
      resetCancel();
      send('factoryReset');
    }
  }

  // Pairing(未接続でも可。接続して 8200 を送る)
  function onPair2(){ send('connectAndPair'); }

  // Factory Reset(未接続でも可。接続して 8300。2タップ確認)
  var reset2Armed=false, reset2Timer=null;
  function reset2Cancel(){
    reset2Armed=false; if(reset2Timer){ clearTimeout(reset2Timer); reset2Timer=null; }
    var b=$('resetBtn2'); if(b){ b.textContent=t('factoryReset2'); b.style.color='#cf8a78'; }
  }
  function onReset2(){
    if(!reset2Armed){
      reset2Armed=true;
      $('resetBtn2').textContent=t('resetConfirm2');
      $('resetBtn2').style.color='#E0876B';
      reset2Timer=setTimeout(reset2Cancel, 4000);
    } else {
      reset2Cancel();
      send('connectAndReset');
    }
  }

  var PLAY_SVG  = '<svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
  var PAUSE_SVG = '<svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>';
  function fmt(s){ s=Math.max(0,Math.floor(s||0)); var m=Math.floor(s/60); var ss=s%60; return m+':'+(ss<10?'0':'')+ss; }

  // ---- knob paint helper (conic ring + rotating dial + glow) ----
  function paintKnob(kind, t, glow){
    var rgb = kind==='vol' ? '74,222,128' : '203,213,205';
    var outer=document.getElementById(kind+'Outer');
    var ring=document.getElementById(kind+'Ring');
    var dial=document.getElementById(kind+'Dial');
    if(!outer||!ring||!dial) return;
    var angle=-135 + t*270;                 // -135deg..+135deg
    var arc=(t*0.75).toFixed(3);            // 0..0.75turn
    ring.style.background='conic-gradient(from 225deg, rgba('+rgb+',.55) 0turn, rgba('+rgb+',.55) '+arc+'turn, rgba(255,255,255,.05) '+arc+'turn, rgba(255,255,255,.05) .75turn, transparent .75turn)';
    dial.style.transform='rotate('+angle+'deg)';
    outer.style.boxShadow='inset 0 2px 6px rgba(255,255,255,.05), 0 8px 18px rgba(0,0,0,.5), 0 0 22px rgba('+rgb+','+glow+')';
  }

  // ---- volume knob (macOS system volume 0-100) ----
  var vol=50, VOL_STEP=5, volLockUntil=0;
  function paintVol(v){ vol=v; $('volVal').textContent=v; paintKnob('vol', v/100, 0.1+(v/100)*0.28); }
  function volChange(d){
    var nv=Math.max(0,Math.min(100,vol+d));
    if(nv===vol) return;
    vol=nv; paintVol(vol); send('volume', vol); volLockUntil=Date.now()+800;
  }

  // ---- bass knob (local -5..+5, one-way BLE commands) ----
  var bass=0;
  function paintBass(v){ bass=v; $('bassVal').textContent=(v>0?'+':'')+v; paintKnob('bass', (v+5)/10, 0.06+Math.abs(v)*0.03); }
  function bassChange(d){
    var nv=Math.max(-5,Math.min(5,bass+d));
    if(nv===bass) return;
    var old=bass; bass=nv; paintBass(bass);
    var steps=Math.abs(nv-old);
    for(var i=0;i<steps;i++) send(d>0?'bassUp':'bassDown');
  }

  // ---- hold-to-repeat for +/- buttons ----
  function setupRepeat(btnId, step, fn){
    var btn=document.getElementById(btnId), timer=null, iv=null;
    function clear(){ if(timer){clearTimeout(timer);timer=null;} if(iv){clearInterval(iv);iv=null;} }
    btn.addEventListener('pointerdown', function(e){ e.preventDefault(); clear(); fn(step);
      timer=setTimeout(function(){ iv=setInterval(function(){ fn(step); }, 100); }, 400); });
    btn.addEventListener('pointerup', clear);
    btn.addEventListener('pointerleave', clear);
    btn.addEventListener('pointercancel', clear);
  }
  setupRepeat('volInc', VOL_STEP, volChange);
  setupRepeat('volDec', -VOL_STEP, volChange);
  setupRepeat('bassInc', 1, bassChange);
  setupRepeat('bassDec', -1, bassChange);

  paintVol(vol);
  paintBass(bass);

  // ---- state from Python ----
  function applyState(s){
    if(s.lang && s.lang!==lang){ lang=s.lang; applyLang(); }
    var connected=!!s.connected;
    $('dot').style.background = connected ? '#7FD79B' : (s.connecting ? '#7FE0A3' : '#6b6b6b');
    $('dot').style.boxShadow  = connected ? '0 0 8px #7FD79B' : 'none';
    $('status').textContent = s.connecting ? t('statusConnecting') : (connected ? t('statusConnected') : t('statusDisconnected'));
    // BLE 依存コントロールのみ接続状態で有効化。Spotify・音量は常に操作可能。
    var ble=$('bleControls');
    ble.style.opacity = connected ? '1' : '.35';
    ble.style.pointerEvents = connected ? 'auto' : 'none';
    // BASS は音量と横並びのため、接続状態で個別にゲートする。
    var bctrl=$('bassCtrl');
    if(bctrl){ bctrl.style.opacity = connected ? '1' : '.35'; bctrl.style.pointerEvents = connected ? 'auto' : 'none'; }
    $('connectArea').style.display = connected ? 'none' : 'block';
    $('connectBtn').textContent = s.connecting ? t('connectBtnConnecting') : t('connect');

    // Spotify チップ
    var sp=!!s.spotify;
    var spCol = sp ? '#7FE0A3' : '#7a857a';
    $('spChipLabel').style.color = spCol;
    $('spChipLabel').textContent = sp ? 'Spotify' : t('spNotConnectedLabel');
    $('spChip').style.background = sp ? 'rgba(107,203,139,.12)' : 'rgba(255,255,255,.03)';
    $('spChip').style.borderColor = sp ? 'rgba(107,203,139,.4)' : 'rgba(255,255,255,.08)';

    // 再生部 or プレースホルダ
    $('playback').style.display = sp ? 'block' : 'none';
    $('spPlaceholder').style.display = sp ? 'none' : 'flex';
    if(s.spotifyInstalled===false) $('spPhText').textContent = t('spNotFound');

    if(sp){
      var playing=!!s.playing;
      $('disc').style.animationPlayState = playing ? 'running' : 'paused';
      $('playIcon').innerHTML = playing ? PAUSE_SVG : PLAY_SVG;
      if(s.title!==undefined) $('npTitle').textContent = s.title || '—';
      if(s.artist!==undefined) $('npArtist').textContent = s.artist || 'Spotify';
      var dur=s.duration||0, pos=s.position||0;
      $('progFill').style.width = (dur>0 ? Math.min(100,pos/dur*100) : 0)+'%';
      $('elapsed').textContent = fmt(pos);
      $('total').textContent = fmt(dur);
    }

    // volume(ボタン操作直後 800ms は上書きしない。その後は実値に追従)
    if(Date.now()>volLockUntil && s.volume!==undefined && s.volume!==null) paintVol(s.volume);

    // input segmented
    ['BT','AUX','USB'].forEach(function(k){
      var b=$('in'+k); if(!b) return;
      var active = s.input===k;
      b.style.background = active ? 'linear-gradient(150deg,#7FE0A3,#2F9E5F)' : 'transparent';
      b.style.color = active ? '#08160d' : '#94a08f';
      b.style.boxShadow = active ? '0 4px 10px -3px rgba(107,203,139,.6)' : 'none';
    });

    if(s.msg!==undefined) $('msg').textContent = s.msg || '';
    requestResize();
  }
  window.applyState = applyState;

  // 内容の高さをネイティブ側へ通知してポップオーバーを実寸にリサイズ
  var lastH=0;
  function requestResize(){
    var h=Math.ceil($('card').getBoundingClientRect().height);
    if(h>0 && Math.abs(h-lastH)>1){ lastH=h; send('size', h); }
  }
  window.addEventListener('load', function(){ applyLang(); requestResize(); });
</script>
</body>
</html>
"""
