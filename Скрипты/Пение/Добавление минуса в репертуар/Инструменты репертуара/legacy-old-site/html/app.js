
let songs=[];
let config={};
let activeTag="все";
let query="";
const selected=new Set();

const tagsEl=document.getElementById("tags");
const listEl=document.getElementById("song-list");
const countEl=document.getElementById("count");
const searchEl=document.getElementById("search");
const template=document.getElementById("song-template");

const selectionBarEl=document.getElementById("selection-bar");
const selectedCountEl=document.getElementById("selected-count");
const sendModalEl=document.getElementById("send-modal");
const modalSongListEl=document.getElementById("modal-song-list");
const modalCopyEl=document.getElementById("modal-copy");
const modalCopyStatusEl=document.getElementById("modal-copy-status");

function songId(s){return `${s.artist}\u0000${s.title}`;}

function pluralize(n){
 const n10=n%10,n100=n%100;
 if(n10===1&&n100!==11)return `${n} композиция`;
 if([2,3,4].includes(n10)&&![12,13,14].includes(n100))return `${n} композиции`;
 return `${n} композиций`;
}

function tagCounts(){
 const c={};
 songs.forEach(s=>(s.tags||[]).forEach(t=>c[t]=(c[t]||0)+1));
 return c;
}

function renderTags(){
 tagsEl.innerHTML="";
 const counts=tagCounts();
 let tags=Object.keys(config.tags||{}).filter(t=>counts[t]);
 tags.sort((a,b)=>{
   const ga=config.groups?.[config.tags[a].group]?.weight||0;
   const gb=config.groups?.[config.tags[b].group]?.weight||0;
   return gb-ga || (config.tags[b].weight||0)-(config.tags[a].weight||0);
 });
 ["все",...tags].forEach(t=>{
   const b=document.createElement("button");
   b.className="tag-button"+(activeTag===t?" active":"");
   b.type="button";
   if(t==="все") b.textContent="Все";
   else{
    b.innerHTML=`${t}<sup>${counts[t]}</sup>`;
    const group=config.groups?.[config.tags[t].group];
    if(group?.color && activeTag!==t)b.style.backgroundColor=group.color;
   }
   b.onclick=()=>{activeTag=t;renderTags();renderSongs(); if(window.innerWidth<=720) document.getElementById("song-list").scrollIntoView({behavior:"smooth",block:"start"});};
   tagsEl.appendChild(b);
 });
}

function filteredSongs(){
 const q=query.toLowerCase().trim();
 const hit=config.settings?.hit_rating||242;
 return songs.filter(s=>{
  return (activeTag==="все"||(s.tags||[]).includes(activeTag)) &&
  (!q||`${s.artist} ${s.title}`.toLowerCase().includes(q));
 }).sort((a,b)=>{
  const ah=a.rating>=hit?1:0,bh=b.rating>=hit?1:0;
  return bh-ah || (b.rating||0)-(a.rating||0) ||
   (a.artist||"").localeCompare(b.artist||"","ru") ||
   (a.title||"").localeCompare(b.title||"","ru");
 });
}

function renderSongs(){
 const arr=filteredSongs();
 countEl.textContent=pluralize(arr.length);
 listEl.innerHTML="";
 arr.forEach(s=>{
  const node=template.content.cloneNode(true);
  const input=node.querySelector(".song-checkbox");
  const text=node.querySelector(".song-text");
  text.textContent=`${s.rating>=(config.settings?.hit_rating||242)?"⭐ ":""}${s.artist} – ${s.title}`;
  input.checked=selected.has(songId(s));
  input.onchange=()=>{input.checked?selected.add(songId(s)):selected.delete(songId(s));updateBar();};
  listEl.appendChild(node);
 });
 updateBar();
}

function updateBar(){
 selectionBarEl.hidden=selected.size===0;
 selectedCountEl.textContent=`Выбрано: ${selected.size}`;
}

function selectedSongs(){
 return songs.filter(s=>selected.has(songId(s)));
}

function buildMessage(){
 return selectedSongs().map((s,i)=>`${i+1}. ${s.artist} – ${s.title}`).join("\n");
}

function openModal(){
 modalSongListEl.innerHTML="";
 selectedSongs().forEach((s,i)=>{
  let d=document.createElement("div");
  d.className="selected-song-item";
  d.textContent=`${i+1}. ${s.artist} – ${s.title}`;
  modalSongListEl.appendChild(d);
 });
 sendModalEl.hidden=false;
 document.body.classList.add("modal-open");
}
function closeModal(){sendModalEl.hidden=true;document.body.classList.remove("modal-open");}

async function copyList(){
 await navigator.clipboard.writeText(buildMessage());
 modalCopyEl.textContent="Скопировано ✓";
 modalCopyStatusEl.textContent="Теперь выберите мессенджер.";
}

document.getElementById("send-telegram").onclick=openModal;
modalCopyEl.onclick=copyList;
sendModalEl.onclick=e=>{if(e.target.dataset.closeModal!==undefined)closeModal();};
searchEl.oninput=e=>{query=e.target.value;renderSongs();};

const hitBtn=document.createElement("button");
hitBtn.className="link-button";
hitBtn.type="button";
hitBtn.textContent="⭐ Выбрать все хиты";
document.querySelector(".summary-actions").appendChild(hitBtn);
hitBtn.onclick=()=>{
 const hit=config.settings?.hit_rating||242;
 songs.filter(s=>s.rating>=hit).forEach(s=>selected.add(songId(s)));
 renderSongs();
};

function init(){
 if(!window.REPERTOIRE){listEl.innerHTML="Ошибка songs.js";return;}
 songs=window.REPERTOIRE.songs;
 config=window.REPERTOIRE.config;
 renderTags();renderSongs();
}
init();


function scrollToSongs(){
  const el=document.querySelector('.songs, #songs, .song-list');
  if(el) el.scrollIntoView({behavior:'smooth', block:'start'});
}
