// Exercise the compiled content script using focused DOM and Chrome fixtures.
// Input attributes reflect the two supported documentation layouts.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor(tag, attrs={}, form=null) {
    this.tag=tag; this.attrs=attrs; this.form=form;
    this.id=attrs.id || ''; this.name=attrs.name || '';
    this.type=attrs.type || 'text'; this.value=attrs.value || '';
    this.classList={contains:name=>(attrs.class || '').split(' ').includes(name)};
  }
  getAttribute(name){return this.attrs[name] ?? null}
  closest(tag){return tag === 'form' ? this.form : null}
}
function field(attrs, form=null){return new Element('input',attrs,form && new Element('form',form))}
function probe(nodes, href='https://docs.python.org/3/library/json.html') {
  const listeners = {};
  const document={
    readyState:'complete',
    addEventListener(type, callback){listeners[type]=callback},
    querySelectorAll(selector){return nodes.filter(node=>selector.split(',').includes(node.tag))},
    querySelector(selector){
      return nodes.find(node=>selector.split(',').some(part=>part === node.tag
        || (part === '[contenteditable]:not([contenteditable="false"])'
          && node.getAttribute('contenteditable') !== null && node.getAttribute('contenteditable') !== 'false')));
    },
  };
  let respond;
  vm.runInNewContext(fs.readFileSync('dist/probe.js','utf8'), {
    document, Element, location:new URL(href), URL, Date,
    chrome:{runtime:{onMessage:{addListener(callback){respond=callback}},sendMessage(){return Promise.resolve()}}},
  });
  return {listeners,state(){let result;respond({type:'probe'},{},value=>{result=value});return result}};
}
const searchForm={method:'get',action:'../search.html'};

test('Python navigation and empty search do not prevent release',()=>{
  const nav=field({type:'checkbox',id:'menuToggler',class:'toggler__input','aria-controls':'navigation'});
  const page=probe([nav,field({type:'search',name:'q'},searchForm),field({type:'submit'})]);
  assert.equal(page.state().interactive,false);
  page.listeners.change({isTrusted:true,target:nav});
  assert.equal(page.state().dirty,false);
});

test('Qt sidebar toggles and its text search have known read-only behavior',()=>{
  const page=probe([
    field({type:'checkbox',class:'sidebar-toggle',id:'__navigation'}),
    field({type:'checkbox',class:'toctree-checkbox',id:'toctree-checkbox-1'}),
    field({name:'q',class:'sidebar-search'},searchForm),
  ],'https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html');
  assert.equal(page.state().interactive,false);
});

test('unknown forms and all editable content remain protected',()=>{
  for(const node of [field({}),field({type:'checkbox',id:'unrelated'}),
    new Element('textarea'),new Element('select'),new Element('div',{contenteditable:''}),
    new Element('div',{contenteditable:'plaintext-only'}),field({name:'q'},{action:'/submit',method:'post'})]) {
    assert.equal(probe([node]).state().interactive,true);
  }
});

test('typed search remains protected even when its text is later cleared',()=>{
  const input=field({type:'search',name:'q'},searchForm);
  const page=probe([input]);
  input.value='unfinished search';
  assert.equal(page.state().interactive,true);
  page.listeners.input({isTrusted:true,target:input});
  input.value='';
  assert.equal(page.state().dirty,true);
});

test('frames and playing media retain independent protection signals',()=>{
  const video=new Element('video'); video.paused=false;
  const page=probe([new Element('iframe'),video]);
  assert.equal(page.state().frames,true);
  assert.equal(page.state().media,true);
});
