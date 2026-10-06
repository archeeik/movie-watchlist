/* 보고싶은 영화 — data/*.json을 읽어 그린다. 하트·내 별점은 localStorage("mine")에 저장. */
const DATA="data/";
let FILMS=[];                       // data/films.json
let state={scrDate:"",scr:{},ott:{}}; // data/status.json
let NOW={days:{}};                  // data/showtimes.json
let REVIEWS={};                     // data/reviews.json: {id: [[평론가, 별점, 한줄평], ...]} — 한줄평을 받아 둔 작품만

// 내 기록: st[id] = "want"(보고 싶은 영화) | "seen"(본 영화), rt[id] = 내 별점(0.5~5, 빈 하트로 돌려도 유지),
// ts[id] = 그 영화의 기록을 마지막으로 바꾼 시각(기기 간 동기화에서 영화별로 더 새로운 쪽을 고르는 데 씀)
let MINE={st:{},rt:{},ts:{}};
try{ const s=JSON.parse(localStorage.getItem("mine")||"null"); if(s&&s.st) MINE={st:s.st,rt:s.rt||{},ts:s.ts||{},at:s.at||0}; }catch(e){}
const STAR_ROW=(cls)=>`<svg class="${cls}" viewBox="0 0 110 22" aria-hidden="true">${[0,1,2,3,4].map(i=>`<path transform="translate(${i*22} 0)" d="M11 1.8l2.7 5.6 6.1.9-4.4 4.3 1 6.1L11 15.8l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>`).join("")}</svg>`;
let sortBy="new", filter="all", mineOnly=false, query="", yearSel=null;   // yearSel: 연도 탭에서 고른 개봉 연도
try{ mineOnly=localStorage.getItem("f:mine")==="1"; }catch(e){}
const todayStr=()=>{ const n=new Date(); return `${n.getFullYear()}-${String(n.getMonth()+1).padStart(2,"0")}-${String(n.getDate()).padStart(2,"0")}`; };
let TODAY=todayStr();   // 앱을 켜 둔 채 날짜가 바뀌면 돌아올 때 다시 정한다
let loadedAt=0;
const $=s=>document.querySelector(s);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

function isFuture(f){ if(!f.d) return false; const d=f.d.length===7? f.d+"-01" : f.d; return d>TODAY; }
function statusOf(f){
  const [scr,last]=state.scr[f.id]||[0,""];
  if(isFuture(f)) return {k:"soon",label: f.d.length===7?`${+f.d.slice(5)}월 개봉 예정`:"개봉 예정", extra: scr?`사전 상영 ${scr}개관`:""};
  if(scr>0) return {k:"on",label:`상영중 ${scr.toLocaleString()}개관`};
  if(last) return {k:"part",label:`간헐 상영 · 최근 ${+last.slice(0,2)}/${+last.slice(3)}`};
  const rel=f.d&&f.d.length===10?f.d:(f.d?f.d+"-01":"");
  const scrDay=state.scrDay||((state.scrAt||TODAY).slice(0,4)+"-"+state.scrDate);
  if(rel && state.scrDate && rel>scrDay) return {k:"part",label:"개봉 · 상영 정보 미확인"};
  return {k:"off",label:"종영"};
}
function fcat(f){const s=statusOf(f).k; return s==="part"?"off":s;}
function fmtDate(f){
  if(f.re) return `${f.y}년작 재개봉`;
  if(f.d.length===7) return `${+f.d.slice(0,4)}년 ${+f.d.slice(5)}월 개봉`+(isFuture(f)?" 예정":"")+(f.rr?` · ${esc(f.rr)}`:"");
  const [y,m,d]=f.d.split("-"); return `${+y}년 ${+m}월 ${+d}일 개봉`+(f.rr?` · ${esc(f.rr)}`:"")+(f.ex?" · 기준 외 추가":"");
}
// OTT: 구독으로 볼 수 있는 플랫폼만 이름으로 표시하고, 단품은 플랫폼과 무관하게 '구매 가능' 여부만 표시한다
const OTT_NAMES=[["n","넷플릭스","nfx"],["w","왓챠","wac"],["t","티빙","tvi"],["v","웨이브","wav"],["d","디즈니+","dis"],["a","애플TV","apl"]];
function ottTags(f){
  if(isFuture(f)) return `<span class="tag no">OTT 개봉 전</span>`;
  const o=state.ott[f.id]||{}, s=o.s||"";
  let h=OTT_NAMES.filter(([c])=>s.includes(c)).map(([,name,cls])=>`<span class="tag ${cls}">${name}</span>`).join("");
  if(o.b) h+=`<span class="tag buy">단품 구매</span>`;
  if(!h) h=`<span class="tag no">OTT 없음</span>`;
  if(o.u) h+=`<span class="tag unk" title="제목이 같은 다른 영화의 정보일 수 있습니다">동명 주의</span>`;
  return h;
}
const HEART=`<svg class="i-heart" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20.5s-7.5-4.6-9.3-9.4C1.5 7.8 3.6 4.5 7 4.5c2 0 3.5 1.1 5 3 1.5-1.9 3-3 5-3 3.4 0 5.5 3.3 4.3 6.6-1.8 4.8-9.3 9.4-9.3 9.4z"/></svg>`;
const SEEN=`<svg class="i-seen" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="M7.5 12.3l3 3 6-6.3"/></svg>`;
const stLabel=s=>s==="want"?"보고 싶은 영화":s==="seen"?"본 영화":"표시 안 함";
function rateHTML(f){ const v=MINE.rt[f.id]||0;
  return `<span class="mylab">내 별점</span><span class="stars" role="group" aria-label="${esc(f.t)} 내 별점">${STAR_ROW("s-bg")}<span class="s-fg" style="width:${v/5*100}%">${STAR_ROW("")}</span><span class="s-hit">${Array.from({length:10},(_,i)=>`<button data-star="${f.id}" data-v="${(i+1)/2}" aria-label="${(i+1)/2}점" aria-pressed="${v===(i+1)/2}"></button>`).join("")}</span></span><span class="myval">${v?v.toFixed(1):"별점을 눌러 주세요"}</span>`; }
function rowHTML(f){
  const st=statusOf(f);
  const l2=[f.dir&&("감독 "+f.dir), f.cast, f.c, f.min&&(f.min+"분")].filter(Boolean).join(" · ");
  return `<li class="row" data-id="${f.id}">
    <div class="left">${f.p?`<img class="poster" alt="${esc(f.t)} 포스터" src="${esc(posterURL(f.p))}" width="52" height="75" loading="lazy" decoding="async" referrerpolicy="no-referrer">`:`<div class="poster"></div>`}
      ${REVIEWS[f.id]?`<button class="rate ratebtn" data-reviews="${f.id}" aria-expanded="false" aria-label="${esc(f.t)} 전문가 별점 ${(+f.s).toFixed(2)}, 누르면 한줄평 ${REVIEWS[f.id].length}개 보기"><b>★</b> ${(+f.s).toFixed(2)}</button>`:`<span class="rate"><b>★</b> ${(+f.s).toFixed(2)}</span>`}</div>
    <div class="body">
      <p class="title"><a href="${naver(f)}" target="_blank" rel="noopener">${esc(f.t)}</a></p>
      <div class="l1"><span>${fmtDate(f)}</span></div>
      <div class="l2">${esc(l2)}</div>
      <div class="tags" data-status>${`<span class="tag ${st.k}">${st.label}</span>`+(st.extra?`<span class="tag">${st.extra}</span>`:"")}${ottTags(f)}</div>
      <div class="myrate" data-rate="${f.id}" ${MINE.st[f.id]==="seen"?"":"hidden"}>${rateHTML(f)}</div>
      ${REVIEWS[f.id]?`<div class="reviews" data-rvbox="${f.id}" hidden></div>`:""}
    </div>
    <div class="acts">
      <button class="hbtn" data-mine="${f.id}" data-st="${MINE.st[f.id]||""}" aria-label="${esc(f.t)} 내 기록: ${stLabel(MINE.st[f.id])}" title="누를 때마다 보고 싶은 영화 → 본 영화 → 해제">${HEART}${SEEN}</button>
    </div></li>`;
}
const naver=f=>"https://search.naver.com/search.naver?query="+encodeURIComponent("영화 "+(f.q||f.t));
// 포스터 아래 별점을 누르면 씨네21 전문가 한줄평을 펼친다(한줄평을 받아 둔 작품만)
function reviewsHTML(id){
  return `<ul>${REVIEWS[id].map(([name,score,text])=>`<li><span class="rvhead"><b>★</b> ${esc(score)} <span class="rvname">${esc(name)}</span></span><span class="rvtext">${esc(text)}</span></li>`).join("")}</ul>
    <a class="rvsrc" href="https://cine21.com/movie/info/?movie_id=${encodeURIComponent(id)}" target="_blank" rel="noopener">씨네21 전문가 별점 ↗</a>`;
}
document.addEventListener("click",e=>{
  const b=e.target.closest("[data-reviews]"); if(!b) return;
  const id=b.dataset.reviews, box=document.querySelector(`[data-rvbox="${id}"]`); if(!box) return;
  if(box.hidden&&!box.innerHTML) box.innerHTML=reviewsHTML(id);
  box.hidden=!box.hidden; b.setAttribute("aria-expanded",!box.hidden);
});
// 씨네21 포스터 주소의 크기 표시 [X104,150]를 %5B…%5D로 바꾼다(대괄호가 든 주소를 못 여는 브라우저 대비)
function posterURL(u){ return String(u).replace(/\[/g,"%5B").replace(/\]/g,"%5D"); }
// 포스터를 불러오지 못하면 빈 칸으로
document.addEventListener("error",e=>{ const t=e.target; if(t&&t.tagName==="IMG"&&t.classList.contains("poster")){ const d=document.createElement("div"); d.className="poster"; t.replaceWith(d); } },true);

/* ---------- 상영중: 영화관 시간표 (씨네큐브 광화문 · 에무시네마 · 아리랑시네센터 · CGV 대학로) ---------- */
const ALL_THEATERS=[["cube","씨네큐브 광화문"],["emu","에무시네마"],["ari","아리랑시네센터"],["cgv","CGV 대학로"]];
let THEATERS=ALL_THEATERS;   // 시간표 데이터에 있는 극장만(불러온 뒤 정함)
let nowDay=null;
let NOW_OPEN=(()=>{ try{ return localStorage.getItem("sec:now")!=="0"; }catch(e){ return true; } })();
const nowOpen=()=>NOW_OPEN;
const hm=s=>{const [a,b]=s.split(":").map(Number); return a+b/60;};
const nz2=s=>s.replace(/[\s:,.?!·\-&()'"]/g,"").toLowerCase();
function filmFor(title){ const k=nz2(title); return FILMS.find(f=>nz2(f.t)===k) || FILMS.find(f=>{const a=nz2(f.t); return a.length>2&&(a.startsWith(k)||k.startsWith(a));}); }
const fmtAt=s=>{ const d=new Date(s); return isNaN(d)?"":`${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}`; };
function renderNow(){
  const box=$("#now"); let days=Object.keys(NOW.days||{}).sort(); if(days.some(x=>x>=TODAY)) days=days.filter(x=>x>=TODAY); if(!days.length){ box.innerHTML=""; return; }
  if(!nowDay||!NOW.days[nowDay]||!days.includes(nowDay)) nowDay=days.find(d=>d>=TODAY)||days[days.length-1];
  const open=nowOpen(); const D=NOW.days[nowDay];
  const all=THEATERS.flatMap(([k])=>D[k]||[]);
  let h0=Math.max(8,Math.floor(Math.min(...all.map(s=>hm(s[0])),10))), h1=Math.min(26,Math.ceil(Math.max(...all.map(s=>hm(s[1])),22)));
  const PX=74, W=(h1-h0)*PX, LW=52;   // LW: 왼쪽 관 이름 칸 폭(style.css의 .tlgrid와 같게)
  const wd=d=>["일","월","화","수","목","금","토"][new Date(d+"T00:00:00").getDay()];
  const lab=d=>d===TODAY?"오늘":`${+d.slice(5,7)}/${+d.slice(8)} (${wd(d)})`;
  const upd=NOW.at?`${fmtAt(NOW.at)} 기준`:"";
  const nowH=(()=>{const n=new Date(); return n.getHours()+n.getMinutes()/60;})();
  const ticks=Array.from({length:h1-h0+1},(_,i)=>`<div class="tick" style="left:${i*PX}px">${i<h1-h0?`<span>${(h0+i)%24}시</span>`:""}</div>`).join("");
  const lines=Array.from({length:h1-h0+1},(_,i)=>`<div class="tick" style="left:${i*PX}px"></div>`).join("");
  let rows=`<div class="tlh hd"></div><div class="trk hd" style="width:${W}px">${ticks}</div>`;
  for(const [k,name] of THEATERS){
    const L=D[k]||[]; const screens=[...new Set(L.map(s=>s[3]))].sort();
    rows+=`<div class="tlh th">${name}</div>`;
    if(!screens.length){ const pub=(NOW.pub||{})[k]; const msg=pub&&nowDay>pub?"아직 시간표가 공개되지 않았습니다":"휴관이거나 상영 일정이 없습니다"; rows+=`<div class="tlh">—</div><div class="trk" style="width:${W}px"><div class="closed">${msg}</div></div>`; continue; }
    for(const sc of screens){
      const blks=L.filter(s=>s[3]===sc).map(([a,b,t])=>{
        const f=filmFor(t); const st=f?(MINE.st[f.id]||""):""; const past=nowDay===TODAY&&hm(b)<nowH;
        const cls=["blk",f?"inlist":"",st==="want"?"want":"",st==="seen"?"seen":"",past?"past":""].filter(Boolean).join(" ");
        const x=(hm(a)-h0)*PX, w=Math.max(28,(hm(b)-hm(a))*PX-3);
        const tag=f?`button type="button" data-goto="${f.id}"`:"div"; const T=esc(t), S=esc(sc);
        return `<${tag} class="${cls}" style="left:${x}px;width:${w}px" title="${a}–${b} ${T} · ${name} ${S}" aria-label="${a}부터 ${b}까지 ${T}, ${name} ${S}${st==="want"?", 보고 싶은 영화":st==="seen"?", 본 영화":""}"><b>${st==="want"?"♥ ":""}${T}</b><i>${a}–${b}</i></${tag.split(" ")[0]}>`;
      }).join("");
      // 아트관(세 예술영화관의 모든 관 + CGV 대학로 아트하우스관)은 관 이름을 파란색으로, '아트하우스' 글자는 뺀다
      const art=k!=="cgv"||sc.includes("아트하우스");
      rows+=`<div class="tlh${art?" art":""}"${art&&k==="cgv"?` aria-label="${esc(sc)}"`:""}>${esc(sc.replace(/\s*아트하우스/,""))}</div><div class="trk" style="width:${W}px">${lines}${blks}</div>`;
    }
  }
  const line=nowDay===TODAY&&nowH>h0&&nowH<h1?`<div class="nowline" style="left:${LW+(nowH-h0)*PX}px"></div>`:"";
  box.innerHTML=`<section class="section" data-k="now" data-open="${open}">
    <div class="headrow"><button class="sechead" aria-expanded="${open}"><svg class="chev" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><h2>상영중</h2><span class="cnt">${THEATERS.length}개 극장</span></button></div>
    <div class="group nowwrap">
      <div class="daybar" role="group" aria-label="날짜">${days.map(d=>`<button data-day="${d}" aria-pressed="${d===nowDay}">${lab(d)}<span style="opacity:.6;margin-left:4px;font-variant-numeric:tabular-nums">${THEATERS.reduce((n,[k])=>n+((NOW.days[d]||{})[k]||[]).length,0)}</span></button>`).join("")}<span class="upd">${upd}</span></div>
      <div class="tl" id="tl"><div class="tlgrid">${rows}${line}</div></div>
      <div class="legend"><span class="lw">보고 싶은 영화</span><span class="li">목록에 있는 영화 (누르면 이동)</span><span>그 밖의 상영작</span></div>
    </div></section>`;
  if(open&&nowDay===TODAY){ const tl=$("#tl"); if(tl) tl.scrollLeft=Math.max(0,(nowH-h0-1)*PX); }
}
document.addEventListener("click",e=>{
  const dy=e.target.closest("[data-day]"); if(dy){ nowDay=dy.dataset.day; renderNow(); return; }
  const g=e.target.closest("[data-goto]");
  if(g){ const id=g.dataset.goto; let row=document.querySelector(`.row[data-id="${id}"]`);
    if(!row){ resetFilters(); const f=FILMS.find(x=>String(x.id)===id); if(f) yearSel=f.re?homeYear():f.d.slice(0,4); render(); row=document.querySelector(`.row[data-id="${id}"]`); }
    if(row){ const sec=row.closest(".section"); if(sec&&sec.dataset.open!=="true"){ sec.dataset.open="true"; setOpen(sec.dataset.k,"true"); applyMode(sec); }
      row.hidden=false; row.scrollIntoView({behavior:"smooth",block:"center"}); row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash"); }
    return; }
});

function groupKey(f){ if(f.re) return "re"; const [y,m]=f.d.split("-"); return `${y}-${Math.ceil(+m/3)}`; }
function groupLabel(k){ if(k==="re") return "재개봉·기획전"; const [y,q]=k.split("-"); return `${y}년 ${q}분기`; }
// 섹션 보기 상태: "true"(전체 펼침) → "mine"(보고 싶은·본 영화만) → "false"(접기) → 다시 전체
function openState(k,def){ try{const v=localStorage.getItem("sec:"+k); if(v==="1") return "true"; if(v==="m") return "mine"; if(v==="0") return "false";}catch(e){} return def; }
function setOpen(k,v){ try{localStorage.setItem("sec:"+k,v==="true"?"1":v==="mine"?"m":"0");}catch(e){} }
function applyMode(sec){
  const mode=sec.dataset.open, rows=[...sec.querySelectorAll(".row")];
  let shown=0; rows.forEach(r=>{ const keep=mode!=="mine"||!!MINE.st[r.dataset.id]; r.hidden=!keep; if(keep) shown++; });
  const em=sec.querySelector(".mine-empty"); if(em) em.hidden=!(mode==="mine"&&shown===0);
  const c=sec.querySelector(".cnt"); if(c) c.textContent=mode==="mine"?`내 영화 ${shown} / ${rows.length}편`:`${rows.length}편`;
  const hd=sec.querySelector(".sechead"); if(hd){ hd.setAttribute("aria-expanded",mode!=="false"); hd.setAttribute("aria-label",`${hd.querySelector("h2").textContent}, ${mode==="true"?"전체 보기":mode==="mine"?"보고 싶은 영화와 본 영화만 보기":"접힘"}. 누르면 다음 보기로 바뀝니다`); }
}

// 연도 탭: 목록에 있는 개봉 연도(최신부터). 새 연도의 작품이 들어오면 탭이 저절로 생긴다
const filmYears=()=>[...new Set(FILMS.filter(f=>!f.re&&f.d).map(f=>f.d.slice(0,4)))].sort().reverse();
// 처음 보여 줄 연도: 올해(목록에 있으면), 없으면 올해 이전의 가장 최근 연도. 재개봉·기획전은 이 연도 탭에서만 보인다
function homeYear(){ const ys=filmYears(), cur=TODAY.slice(0,4); return ys.includes(cur)?cur:(ys.find(y=>y<=cur)||ys[0]||cur); }
function renderYears(searching){
  const ys=filmYears(), box=$("#years");
  if(ys.length<2||searching){ box.hidden=true; box.innerHTML=""; return; }   // 검색할 때는 모든 연도에서 찾는다
  box.hidden=false;
  box.innerHTML=ys.map(y=>`<button data-y="${y}" aria-pressed="${y===yearSel}">${y}</button>`).join("");
}
document.addEventListener("click",e=>{ const b=e.target.closest("[data-y]"); if(!b) return; yearSel=b.dataset.y; render(); });

function render(){
  const cmp={new:(a,b)=>(b.d||"").localeCompare(a.d||"")||b.s-a.s, old:(a,b)=>(a.d||"").localeCompare(b.d||"")||b.s-a.s, score:(a,b)=>b.s-a.s||(b.d||"").localeCompare(a.d||"")}[sortBy];
  const reCmp=sortBy==="score"?(a,b)=>b.s-a.s:(sortBy==="old"?(a,b)=>a.y-b.y:(a,b)=>b.y-a.y);
  const groups={};
  const qn=nz2(query);
  if(!yearSel||!filmYears().includes(yearSel)) yearSel=homeYear();
  const inYear=f=>qn||(f.re?yearSel===homeYear():f.d.slice(0,4)===yearSel);
  renderYears(!!qn);
  const hit=f=>!qn||[f.t,f.q,f.dir,f.cast].some(x=>x&&nz2(x).includes(qn));
  // 재개봉·기획전은 상영이 끝난 작품을 목록에서 뺀다(데이터와 하트·별점은 남아 있어 다시 상영하면 돌아온다). 검색할 때는 모두 찾는다
  FILMS.filter(inYear).filter(f=>qn||!(f.re&&statusOf(f).k==="off")).filter(f=>filter==="all"||fcat(f)===filter).filter(f=>!mineOnly||MINE.st[f.id]).filter(hit)
    .forEach(f=>(groups[groupKey(f)]=groups[groupKey(f)]||[]).push(f));
  let keys=Object.keys(groups).filter(k=>k!=="re").sort((a,b)=>sortBy==="old"?a.localeCompare(b):b.localeCompare(a));
  if(groups.re) keys.push("re");
  const box=$("#sections");
  if(!keys.length){box.innerHTML=`<div class="group"><div class="empty">이 조건에 맞는 영화가 없습니다. 검색어나 필터를 바꿔 보세요.</div></div>`;return;}
  box.innerHTML=keys.map(k=>{const list=groups[k].sort(k==="re"?reCmp:cmp); const open=qn?"true":openState(k,k==="re"?"false":"true");
    return `<section class="section" data-k="${k}" data-open="${open}">
      <div class="headrow"><button class="sechead" aria-expanded="${open}"><svg class="chev" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg><h2>${groupLabel(k)}</h2><span class="modebadge">내 영화만</span><span class="cnt">${list.length}편</span></button></div>
      <ul class="group">${list.map(rowHTML).join("")}<li class="empty mine-empty" hidden>이 섹션에 보고 싶은 영화나 본 영화로 표시한 작품이 없습니다. 제목을 다시 누르면 접힙니다.</li></ul></section>`;}).join("");
  box.querySelectorAll(".section").forEach(applyMode);
}
// 마지막 갱신 시각 (자동 갱신 스크립트가 각 JSON에 남긴 시각). 갱신이 오래 멈춰 있으면 주황색으로 알린다
function renderMeta(){
  const day=s=>{ const d=new Date(s); return isNaN(d)?"":`${d.getMonth()+1}/${d.getDate()}`; };
  const old=(s,hours)=>{ const d=new Date(s); return !isNaN(d)&&Date.now()-d>hours*3600e3; };
  const parts=[];
  if(state.scrDate) parts.push([`상영 상태 ${+state.scrDate.slice(0,2)}/${+state.scrDate.slice(3)} 기준`, old(state.scrAt,48)]);
  if(state.ottAt) parts.push([`OTT ${day(state.ottAt)} 확인`, old(state.ottAt,24*10)]);
  if(NOW.at) parts.push([`시간표 ${fmtAt(NOW.at)} 갱신`, old(NOW.at,36)]);
  $("#meta").innerHTML=parts.map(([p,late])=>`<span${late?' class="stale" title="자동 갱신이 늦어지고 있습니다"':""}>${p}${late?" · 갱신 지연":""}</span>`).join("");
}

document.addEventListener("click",e=>{
  const h=e.target.closest(".sechead"); if(h&&h.closest(".section")?.dataset.k==="now"){ const s=h.closest(".section"); NOW_OPEN=s.dataset.open!=="true"; try{localStorage.setItem("sec:now",NOW_OPEN?"1":"0");}catch(err){} renderNow(); return; } if(h){const s=h.closest(".section"); const cur=s.dataset.open; const v=cur==="true"?"mine":cur==="mine"?"false":"true"; s.dataset.open=v; setOpen(s.dataset.k,v); applyMode(s);}
});
document.querySelectorAll("[data-s]").forEach(b=>b.onclick=()=>{sortBy=b.dataset.s;document.querySelectorAll("[data-s]").forEach(x=>x.setAttribute("aria-pressed",x===b));render();});
document.querySelectorAll("[data-f]").forEach(b=>b.onclick=()=>{filter=b.dataset.f;document.querySelectorAll("[data-f]").forEach(x=>x.setAttribute("aria-pressed",x===b));render();});
/* 검색(제목·감독·배우)과 '내 영화'만 보기 */
const paintFilters=()=>{ document.querySelectorAll("[data-f]").forEach(x=>x.setAttribute("aria-pressed",x.dataset.f===filter)); $("#mineOnly").setAttribute("aria-pressed",mineOnly); if($("#q").value.trim()!==query) $("#q").value=query; };
function resetFilters(){ filter="all"; mineOnly=false; query=""; try{localStorage.setItem("f:mine","0");}catch(e){} paintFilters(); }
$("#mineOnly").addEventListener("click",()=>{ mineOnly=!mineOnly; try{localStorage.setItem("f:mine",mineOnly?"1":"0");}catch(e){} paintFilters(); render(); });
let qT; $("#q").addEventListener("input",e=>{ query=e.target.value.trim(); clearTimeout(qT); qT=setTimeout(render,150); });
paintFilters();

let toastT; function toast(m,ms=3200){const t=$("#toast");t.textContent=m;t.dataset.show="true";clearTimeout(toastT);toastT=setTimeout(()=>t.dataset.show="false",ms);}

/* ---------- 내 기록(보고 싶은 영화·본 영화·내 별점) ----------
   화면은 항상 이 페이지의 MINE을 기준으로 즉시 바뀐다. 기록은 이 기기의 localStorage에만 있고,
   다른 기기로는 아래 내보내기·가져오기(mine.json 파일)로 옮긴다. */
function saveLocal(){ try{localStorage.setItem("mine",JSON.stringify(MINE));}catch(e){} }
function saveMine(id){ const now=Date.now(); MINE.at=now; if(id!=null){ MINE.ts=MINE.ts||{}; MINE.ts[id]=now; } saveLocal(); if(SYNC){ clearTimeout(syncT); syncT=setTimeout(syncNow,1500); } }
function validMine(d){ return d && typeof d.st==="object" && d.st && !Array.isArray(d.st); }
// 파일에서 가져오기: 이 기기의 기록을 통째로 바꾼다. 바뀐 모든 영화에 지금 시각을 찍어 동기화에서도 이 내용이 이긴다
function adoptMine(d){ const now=Date.now(), ts={};
  new Set([...Object.keys(MINE.st),...Object.keys(MINE.rt),...Object.keys(d.st),...Object.keys(d.rt||{})]).forEach(id=>ts[id]=now);
  MINE={st:{...d.st},rt:{...(d.rt||{})},ts,at:now}; saveLocal(); if(SYNC){ clearTimeout(syncT); syncT=setTimeout(syncNow,300); } }
// 두 기록을 영화별로 합친다: 영화마다 변경 시각이 더 새로운 쪽을 따른다(같으면 a). ts가 없는 옛 기록은 문서 시각(at)을 쓴다
function mineTime(d,id){ return (d.ts&&d.ts[id]) || (((d.st&&id in d.st)||(d.rt&&id in d.rt))?(d.at||1):0); }
function mergeMine(a,b){ const out={st:{},rt:{},ts:{},at:Math.max(a.at||0,b.at||0)};
  new Set([a,b].flatMap(d=>[...Object.keys(d.st||{}),...Object.keys(d.rt||{}),...Object.keys(d.ts||{})])).forEach(id=>{
    const ta=mineTime(a,id), tb=mineTime(b,id), src=tb>ta?b:a, when=Math.max(ta,tb);
    if(src.st&&src.st[id]) out.st[id]=src.st[id]; if(src.rt&&src.rt[id]) out.rt[id]=src.rt[id]; if(when) out.ts[id]=when; });
  return out; }
const mineKey=d=>JSON.stringify(["st","rt","ts"].map(k=>Object.entries(d[k]||{}).sort(([x],[y])=>x<y?-1:1)));
function paintMine(id){
  try{
    const f=FILMS.find(x=>String(x.id)===String(id)); if(!f) return;
    const b=document.querySelector(`[data-mine="${id}"]`); if(b){ b.setAttribute("data-st",MINE.st[id]||""); b.setAttribute("aria-label",`${f.t} 내 기록: ${stLabel(MINE.st[id])}`); }
    const r=document.querySelector(`[data-rate="${id}"]`); if(r){ r.hidden=MINE.st[id]!=="seen"; r.innerHTML=rateHTML(f); }
  }catch(e){}
}
document.addEventListener("click",e=>{
  const s=e.target.closest("[data-star]");
  if(s){ const id=s.dataset.star; MINE.rt[id]=+s.dataset.v; paintMine(id); saveMine(id);
    const nb=document.querySelector(`[data-star="${id}"][data-v="${s.dataset.v}"]`); if(nb) nb.focus(); return; }
  const b=e.target.closest("[data-mine]"); if(!b) return;
  const id=b.getAttribute("data-mine"); const cur=MINE.st[id]||"";
  const next=cur===""?"want":cur==="want"?"seen":"";
  if(next) MINE.st[id]=next; else delete MINE.st[id];   // 별점(rt)은 지우지 않고 보관
  paintMine(id); try{ b.classList.remove("pop"); void b.offsetWidth; if(next) b.classList.add("pop"); }catch(err){}
  saveMine(id); renderNow();
});

/* ---------- 내 기록 백업: 내보내기·가져오기 ---------- */
$("#mineExport").addEventListener("click",()=>{
  const a=document.createElement("a");
  a.href=URL.createObjectURL(new Blob([JSON.stringify({at:MINE.at||Date.now(),rt:MINE.rt,st:MINE.st,ts:MINE.ts||{}})],{type:"application/json"}));
  a.download="mine.json"; a.click(); setTimeout(()=>URL.revokeObjectURL(a.href),1000);
});
$("#mineImport").addEventListener("click",()=>$("#mineFile").click());
$("#mineFile").addEventListener("change",async e=>{
  const file=e.target.files[0]; e.target.value=""; if(!file) return;
  try{ const d=JSON.parse(await file.text()); if(!validMine(d)) throw 0;
    const n=Object.keys(d.st).length;
    if(!confirm(`이 기기의 하트·별점을 파일의 기록(${n}편)으로 바꿉니다. 계속할까요?`)) return;
    adoptMine(d); render(); renderNow(); toast(`내 기록 ${n}편을 가져왔습니다.`);
  }catch(err){ toast("내 기록 파일을 읽지 못했습니다. mine.json 형식인지 확인해 주세요."); }
});

/* ---------- 기기 간 동기화: 내 GitHub 비공개 Gist에 내 기록을 저장 ----------
   화면은 항상 이 기기의 MINE이 기준이다. 원격은 구독하지 않고, 앱을 열 때·다시 돌아올 때·기록을 바꾼 직후에만
   한 번 받아 영화별로 합친다(mergeMine: 영화마다 더 나중에 바꾼 쪽). 합친 결과가 다르면 이 기기와 Gist를 각각 고친다. */
const SYNC_FILE="movie-watchlist-mine.json";
let SYNC=null; try{ const s=JSON.parse(localStorage.getItem("sync")||"null"); if(s&&s.token&&s.gist) SYNC=s; }catch(e){}
let syncT=null, syncBusy=false, syncAgain=false, lastSyncErr="";
async function ghApi(path,opt={}){
  const r=await fetch("https://api.github.com"+path,{...opt,cache:"no-store",headers:{Accept:"application/vnd.github+json",Authorization:"Bearer "+SYNC.token,...(opt.body?{"Content-Type":"application/json"}:{})}});
  if(!r.ok){ const e=new Error("HTTP "+r.status); e.status=r.status; throw e; }
  return r.json();
}
const mineDoc=()=>JSON.stringify({at:MINE.at||0,rt:MINE.rt,st:MINE.st,ts:MINE.ts||{}});
async function syncPull(){
  const g=await ghApi("/gists/"+SYNC.gist); const f=(g.files||{})[SYNC_FILE]; if(!f) return null;
  let text=f.content; if(f.truncated&&f.raw_url) text=await (await fetch(f.raw_url,{cache:"no-store"})).text();
  try{ return JSON.parse(text); }catch(e){ return null; }
}
const syncPush=()=>ghApi("/gists/"+SYNC.gist,{method:"PATCH",body:JSON.stringify({files:{[SYNC_FILE]:{content:mineDoc()}}})});
function syncErr(e){ return e.status===401?"토큰이 만료됐거나 올바르지 않습니다. 다시 연결해 주세요":e.status===404?"저장된 기록(Gist)을 찾지 못했습니다. 다시 연결해 주세요":e.status===403?"토큰에 Gist 권한이 없거나 요청이 너무 많습니다":"연결되지 않아 나중에 다시 시도합니다"; }
function setSync(msg){ $("#syncState").textContent=msg; $("#syncBtn").textContent=SYNC?"해제":"설정"; if(SYNC) $("#syncForm").hidden=true; }
async function syncNow(){
  if(!SYNC) return; if(syncBusy){ syncAgain=true; return; } syncBusy=true; clearTimeout(syncT); syncT=null;
  try{
    const d=await syncPull();
    if(validMine(d)){
      const m=mergeMine(MINE,d);
      if(mineKey(m)!==mineKey(MINE)){ MINE=m; saveLocal(); render(); renderNow(); }
      if(mineKey(m)!==mineKey(d)) await syncPush();
    } else await syncPush();
    lastSyncErr=""; setSync(`켜짐 · ${fmtAt(Date.now())} 동기화`);
  }catch(e){ if(SYNC){ const m=syncErr(e); setSync("켜짐 · "+m); if(e.status&&m!==lastSyncErr) toast("동기화 오류: "+m,6000); lastSyncErr=m; } }
  syncBusy=false; if(syncAgain){ syncAgain=false; syncNow(); }
}
async function syncConnect(token){
  SYNC={token}; setSync("연결하는 중…");
  try{
    const list=await ghApi("/gists?per_page=100");
    let g=list.find(x=>x.files&&x.files[SYNC_FILE]);
    if(!g) g=await ghApi("/gists",{method:"POST",body:JSON.stringify({description:"보고싶은 영화 — 내 기록(자동 동기화)",public:false,files:{[SYNC_FILE]:{content:mineDoc()}}})});
    SYNC.gist=g.id; try{ localStorage.setItem("sync",JSON.stringify(SYNC)); }catch(e){}
    $("#syncToken").value=""; await syncNow(); toast("동기화를 켰습니다. 다른 기기에서도 같은 토큰으로 연결해 주세요.",5000);
  }catch(e){ SYNC=null; setSync("꺼짐 · "+syncErr(e)); }
}
$("#syncBtn").addEventListener("click",()=>{
  if(!SYNC){ const f=$("#syncForm"); f.hidden=!f.hidden; if(!f.hidden) $("#syncToken").focus(); return; }
  if(!confirm("이 기기의 동기화를 끕니다. 하트·별점은 이 기기와 Gist에 그대로 남습니다. 계속할까요?")) return;
  SYNC=null; clearTimeout(syncT); try{ localStorage.removeItem("sync"); }catch(e){} setSync("꺼짐");
});
$("#syncGo").addEventListener("click",()=>{ const v=$("#syncToken").value.trim(); if(v) syncConnect(v); });
$("#syncToken").addEventListener("keydown",e=>{ if(e.key==="Enter") $("#syncGo").click(); });
document.addEventListener("visibilitychange",()=>{ if(SYNC && (document.visibilityState==="visible" || syncT)) syncNow(); });
setSync(SYNC?"켜짐":"꺼짐");

/* ---------- 시작: 데이터 불러오기 ---------- */
async function getJSON(name){ const r=await fetch(DATA+name,{cache:"no-cache"}); if(!r.ok) throw new Error(`${name} ${r.status}`); return r.json(); }
async function loadData(){
  const [films,status,shows,reviews]=await Promise.all([getJSON("films.json"),getJSON("status.json"),getJSON("showtimes.json").catch(()=>({days:{}})),getJSON("reviews.json").catch(()=>({}))]);
  FILMS=films; state={scrDate:"",scr:{},ott:{},...status}; NOW=shows; REVIEWS=reviews;
  THEATERS=ALL_THEATERS.filter(([k])=>(NOW.pub||{})[k]||Object.values(NOW.days||{}).some(d=>(d[k]||[]).length));
  loadedAt=Date.now();
}
(async()=>{
  try{ await loadData(); }
  catch(err){ $("#sections").innerHTML=`<div class="group"><div class="empty">작품 정보를 불러오지 못했습니다. 잠시 뒤 다시 열어 주세요. (${esc(err.message)})</div></div>`; return; }
  render(); renderMeta(); renderNow();
  syncNow();
})();
// 앱을 켜 둔 채 다시 돌아왔을 때: 날짜가 바뀌었거나 1시간이 지났으면 데이터를 다시 받고, 현재 시각 선은 항상 다시 그린다
document.addEventListener("visibilitychange",async()=>{
  if(document.visibilityState!=="visible"||!loadedAt) return;
  const dayChanged=todayStr()!==TODAY;
  if(dayChanged||Date.now()-loadedAt>3600e3){ TODAY=todayStr(); if(dayChanged) nowDay=null; try{ await loadData(); }catch(e){} render(); renderMeta(); }
  renderNow();
});

/* ---------- 홈 화면 앱(PWA): 서비스 워커 등록 ---------- */
if("serviceWorker" in navigator) window.addEventListener("load",()=>navigator.serviceWorker.register("sw.js").catch(()=>{}));
