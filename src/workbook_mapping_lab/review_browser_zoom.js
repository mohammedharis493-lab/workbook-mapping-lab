/* Accessibility: browser zoom stays native; added text zoom and pointer magnifier. */
(() => {
'use strict';
const $=id=>document.getElementById(id);
const root=document.documentElement;
const zoom=$('page-zoom');
const zoomOutput=$('zoom-output');
const lensScale=$('lens-scale');
const lensOutput=$('lens-output');
const lens=$('reader-lens');
const lensText=$('lens-text');
const lensToggle=$('lens-toggle');
let active=false;
let pinned=false;
let pointer={x:0,y:0};
let last={phrase:'',word:''};
function bounded(value,min,max){return Math.min(max,Math.max(min,value));}
function setZoom(value){
 const num=bounded(Math.round(value/5)*5,75,250);
 zoom.value=String(num);zoomOutput.textContent=num+'%';
 root.style.fontSize=(16*num/100)+'px';
 try{localStorage.setItem('wml_text_zoom',String(num));}catch{}
}
function setLensZoom(value){
 const num=bounded(Math.round(value/25)*25,150,500);
 lensScale.value=String(num);lensOutput.textContent=num+'%';
 $('lens-multiplier').textContent=num+'%';
 lens.style.setProperty('--lens-font',(num/100*16)+'px');
 try{localStorage.setItem('wml_lens_zoom',String(num));}catch{}
}
function currentText(event){
 const pos=document.caretPositionFromPoint?.(event.clientX,event.clientY);
 const range=(!pos)?document.caretRangeFromPoint?.(event.clientX,event.clientY):null;
 let n=pos?.offsetNode||range?.startContainer||null;
 let off=pos?.offset??range?.startOffset??0;
 if(n?.nodeType!==Node.TEXT_NODE){
  const el=document.elementFromPoint(event.clientX,event.clientY);
  if(el && !el.closest('button,input,select,textarea,nav,.zoom-tools,.lens')){
   const full=el.textContent?.trim().replace(/\s+/g,' ').slice(0,150)||'';
   if(full)return {phrase:full,word:full.slice(0,70)};
  }
  return null;
 }
 let s=n.textContent||'';
 if(!s.trim())return null;
 off=bounded(off,0,s.length);
 // UTF-16 offsets returned by Chrome are respected. Handle common
 // letters, numbers, ₹, punctuation used in financial figures.
 const wordChar=/[\p{L}\p{N}₹.,_%/-]/u;
 let start=off,end=off;
 while(start>0 && wordChar.test(s[start-1]))start--;
 while(end<s.length && wordChar.test(s[end]))end++;
 if(start===end && start>0){start--;end=off;}
 let word=s.slice(start,end).trim();
 if(!word) word=s.trim().slice(0,60);
 const from=Math.max(0,start-45),to=Math.min(s.length,end+45);
 let phrase=s.slice(from,to).replace(/\s+/g,' ').trim();
 if(!phrase)phrase=word;
 return {phrase,word};
}
function showText(message){
 last=message;
 const {phrase,word}=message;
 lensText.replaceChildren();
 const index=phrase.toLocaleLowerCase().indexOf(word.toLocaleLowerCase());
 if(index<0){lensText.textContent=phrase;return;}
 lensText.append(document.createTextNode(phrase.slice(0,index)));
 const mark=document.createElement('mark');mark.textContent=phrase.slice(index,index+word.length);
 lensText.append(mark,document.createTextNode(phrase.slice(index+word.length)));
}
function positionLens(x,y){
 const w=lens.offsetWidth||480;
 const h=lens.offsetHeight||180;
 let left=x+22,top=y+22;
 if(left+w>window.innerWidth-12) left=x-w-20;
 if(top+h>window.innerHeight-12) top=y-h-18;
 lens.style.left=bounded(left,8,Math.max(8,window.innerWidth-w-8))+'px';
 lens.style.top=bounded(top,8,Math.max(8,window.innerHeight-h-8))+'px';
}
function turnOn(value){
 active=value;pinned=false;
 lensToggle.setAttribute('aria-pressed',String(value));
 lensToggle.textContent=value?'Reading lens ON · Alt M':'Reading lens · Alt M';
 lens.hidden=!value;
 if(value){
  showText({phrase:'Move the pointer over a word or amount to enlarge it.',word:'word'});
  positionLens(window.innerWidth/2,window.innerHeight/2);
 }
}
function pointerUpdate(ev){
 if(!active||pinned)return;
 if(ev.target.closest('dialog,.zoom-tools,.header')){lens.hidden=true;return;}
 if(ev.target.closest('input,textarea,select,button')){lens.hidden=true;return;}
 const data=currentText(ev);
 if(!data){lens.hidden=true;return;}
 lens.hidden=false;pointer={x:ev.clientX,y:ev.clientY};
 if(data.phrase!==last.phrase||data.word!==last.word)showText(data);
 positionLens(pointer.x,pointer.y);
}
document.addEventListener('pointermove',pointerUpdate,{passive:true});
document.addEventListener('click',ev=>{
 if(!active||ev.target.closest('dialog,.header,button,input,select,textarea'))return;
 if(pinned){pinned=false;pointerUpdate(ev);}
 else if(!lens.hidden){pinned=true;lens.querySelector('small:last-child').textContent='Pinned · Press Esc to release';}
});
document.addEventListener('keydown',ev=>{
 if(ev.altKey && !ev.ctrlKey && !ev.shiftKey && ev.key.toLowerCase()==='m'){
  ev.preventDefault();turnOn(!active);
 }
 if(ev.key==='Escape' && pinned){
  pinned=false;
  lens.querySelector('small:last-child').textContent='Hover over a word · Click to pin · Esc to unpin';
 }
});
document.addEventListener('focusin',ev=>{
 if(!active||pinned)return;
 const target=ev.target;
 if(!target||target.closest('.header,.lens'))return;
 const text=(target.getAttribute('aria-label')||target.textContent||target.value||'').trim();
 if(text){
  lens.hidden=false;
  showText({phrase:text.slice(0,130),word:text.slice(0,55)});
  const rect=target.getBoundingClientRect();
  positionLens(rect.x+Math.min(rect.width/2,200),rect.y);
 }
});
zoom.addEventListener('input',e=>setZoom(Number(e.target.value)));
lensScale.addEventListener('input',e=>setLensZoom(Number(e.target.value)));
$('smaller').addEventListener('click',()=>setZoom(Number(zoom.value)-10));
$('bigger').addEventListener('click',()=>setZoom(Number(zoom.value)+10));
$('zoom-reset').addEventListener('click',()=>setZoom(100));
lensToggle.addEventListener('click',()=>turnOn(!active));
$('help-zoom').addEventListener('click',()=>$('help-dialog').showModal());
$('help-close').addEventListener('click',()=>$('help-dialog').close());
const stored=(name,fallback)=>{try{return Number(localStorage.getItem(name)||fallback);}catch{return fallback;}};
setZoom(stored('wml_text_zoom',100));
setLensZoom(stored('wml_lens_zoom',280));
})();
