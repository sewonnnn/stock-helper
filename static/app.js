const IS_LOCAL = ['localhost', '127.0.0.1', '0.0.0.0'].includes(window.location.hostname);
const API_BASE = IS_LOCAL ? '' : 'https://stock-helper-t45j.onrender.com';

let isLoading = false, isComposing = false, glossaryHintShown = false, abortController = null, currentLoadingId = null;
let currentThreadId = null;
const STORAGE_KEY = 'stockmentor_conversations';
const MAX_CONVERSATIONS = 50;
const SEND_ICON = `<svg width="16" height="16" fill="none" stroke="#fff" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18"/></svg>`;
const STOP_ICON = `<svg width="16" height="16" fill="#fff" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>`;

// ── 사이드바 토글 (모바일) ──
function toggleSidebar() {
    document.querySelector('.sidebar').classList.toggle('open');
    document.getElementById('sidebarOverlay').classList.toggle('open');
}
function closeSidebar() {
    document.querySelector('.sidebar').classList.remove('open');
    document.getElementById('sidebarOverlay').classList.remove('open');
}

// ── localStorage 헬퍼 ──
function loadStore() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY)) || { conversations: {}, activeId: null }; }
    catch(e) { console.warn('localStorage 읽기 실패:', e); return { conversations: {}, activeId: null }; }
}
function saveStore(store) {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
    } catch (e) {
        console.warn('localStorage 저장 실패:', e);
        const ids = Object.keys(store.conversations);
        if (ids.length > 1) {
            const oldest = ids.sort((a, b) => store.conversations[a].updatedAt - store.conversations[b].updatedAt)[0];
            delete store.conversations[oldest];
            try { localStorage.setItem(STORAGE_KEY, JSON.stringify(store)); } catch (_) {}
        }
    }
}

function createConversation(threadId) {
    const store = loadStore();
    const id = threadId || 'conv_' + Date.now();
    store.conversations[id] = { id, title: '', createdAt: Date.now(), updatedAt: Date.now(), messages: [] };
    store.activeId = id;
    const ids = Object.keys(store.conversations);
    if (ids.length > MAX_CONVERSATIONS) {
        const oldest = ids.sort((a, b) => store.conversations[a].updatedAt - store.conversations[b].updatedAt)[0];
        delete store.conversations[oldest];
    }
    saveStore(store);
    return id;
}

function addMessageToStore(threadId, msg) {
    const store = loadStore();
    const conv = store.conversations[threadId];
    if (!conv) return;
    conv.messages.push(msg);
    conv.updatedAt = Date.now();
    if (!conv.title && msg.role === 'user') conv.title = msg.content.substring(0, 30);
    saveStore(store);
}

function deleteConversation(id) {
    const store = loadStore();
    delete store.conversations[id];
    if (store.activeId === id) store.activeId = null;
    saveStore(store);
    if (currentThreadId === id) { currentThreadId = null; newChat(); }
    renderSidebar();
}

function renderSidebar() {
    const store = loadStore();
    const list = document.getElementById('conversationList');
    const convs = Object.values(store.conversations).sort((a, b) => b.updatedAt - a.updatedAt);
    if (!convs.length) { list.innerHTML = ''; return; }
    list.innerHTML = convs.map(c => {
        const active = c.id === currentThreadId ? ' active' : '';
        const title = c.title || '새 대화';
        return `<div class="conv-item${active}" onclick="loadConversation('${c.id}')"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24" style="flex-shrink:0"><path stroke-linecap="round" stroke-linejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg><span class="conv-title">${escapeHtml(title)}</span><button class="conv-delete" onclick="event.stopPropagation();deleteConversation('${c.id}')"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" d="M6 18L18 6M6 6l12 12"/></svg></button></div>`;
    }).join('');
}

function resetLoadingUI() {
    if (currentLoadingId) {
        const el = document.getElementById(currentLoadingId);
        if (el) el.remove();
        currentLoadingId = null;
    }
    if (loadingInterval) { clearInterval(loadingInterval); loadingInterval = null; }
    isLoading = false;
    setButtonMode('send');
}

function loadConversation(id) {
    closeSidebar();
    const store = loadStore();
    const conv = store.conversations[id];
    if (!conv) return;
    resetLoadingUI();
    currentThreadId = id;
    store.activeId = id;
    saveStore(store);
    const container = document.getElementById('chatContainer');
    container.innerHTML = '';
    glossaryHintShown = false;
    conv.messages.forEach(msg => {
        if (msg.role === 'user') addUserMessage(msg.content);
        else if (msg.role === 'assistant' && msg.data) addBotResponse(msg.data, msg.route);
    });
    document.getElementById('suggestionChips').style.display = conv.messages.length ? 'flex' : 'none';
    container.scrollTop = container.scrollHeight;
    renderSidebar();
}

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('questionInput');
    input.addEventListener('compositionstart', () => { isComposing = true; });
    input.addEventListener('compositionend', () => { isComposing = false; });
    input.addEventListener('keydown', e => { if (e.key === 'Enter' && !isComposing) sendQuestion(); });
    const store = loadStore();
    renderSidebar();
    if (store.activeId && store.conversations[store.activeId]) {
        loadConversation(store.activeId);
    }
});

// ── 용어 사전 (glossary.json에서 로드) ──
const GLOSSARY={}, GLOSSARY_GROUP={};
let GLOSSARY_TERMS = [];
fetch(IS_LOCAL ? '/static/glossary.json' : './glossary.json').then(r=>r.json()).then(data=>{
    data.forEach((e,i)=>e.terms.forEach(t=>{GLOSSARY[t]=e.tip;GLOSSARY_GROUP[t]=i;}));
    GLOSSARY_TERMS = Object.keys(GLOSSARY).sort((a,b)=>b.length-a.length);
});

function highlightTerms(html) {
    const done = new Set();
    const parts = html.split(/(<[^>]+>)/);
    const isAn = c=>/[a-zA-Z0-9]/.test(c);
    return parts.map(p=>{
        if(p.startsWith('<')||!p.trim()) return p;
        let r='',i=0;
        while(i<p.length){
            let f=false;
            for(const t of GLOSSARY_TERMS){
                const g=GLOSSARY_GROUP[t]; if(done.has(g)) continue;
                const l=t.length; if(i+l>p.length) continue;
                if(p.substring(i,i+l).toLowerCase()!==t.toLowerCase()) continue;
                if(/^[a-zA-Z]/.test(t)){
                    const b=i>0?p[i-1]:'', a=i+l<p.length?p[i+l]:'';
                    if(isAn(b)||isAn(a)) continue;
                }
                r+=`<span class="term-tooltip" data-tooltip="${escapeHtml(GLOSSARY[t])}">${p.substring(i,i+l)}</span>`;
                done.add(g); i+=l; f=true; break;
            }
            if(!f){r+=p[i];i++;}
        }
        return r;
    }).join('');
}

let activeTooltip=null, activeTooltipTarget=null;
function showTooltip(el){
    if(activeTooltipTarget===el)return; hideTooltip();
    const rect=el.getBoundingClientRect();
    const tip=document.createElement('div'); tip.className='glossary-tip'; tip.textContent=el.dataset.tooltip;
    document.body.appendChild(tip);
    const tr=tip.getBoundingClientRect();
    let left=rect.left+rect.width/2-tr.width/2, top=rect.top-tr.height-8;
    left=Math.max(8,Math.min(left,window.innerWidth-tr.width-8));
    if(top<4) top=rect.bottom+8;
    tip.style.left=left+'px'; tip.style.top=top+'px';
    activeTooltip=tip; activeTooltipTarget=el;
}
function hideTooltip(){if(activeTooltip){activeTooltip.remove();activeTooltip=null;activeTooltipTarget=null;}}
document.addEventListener('mouseover',e=>{const t=e.target.closest('.term-tooltip');if(t)showTooltip(t);else hideTooltip();});
document.addEventListener('click',e=>{const t=e.target.closest('.term-tooltip');if(t)showTooltip(t);else hideTooltip();});
document.getElementById('chatContainer').addEventListener('scroll',hideTooltip);

const AI_AVATAR = `<div class="ai-avatar"><svg width="18" height="18" fill="#fff" viewBox="0 0 24 24"><path d="M12 2a1 1 0 011 1v2h3a3 3 0 013 3v10a3 3 0 01-3 3H8a3 3 0 01-3-3V8a3 3 0 013-3h3V3a1 1 0 011-1zM8 7a1 1 0 00-1 1v10a1 1 0 001 1h8a1 1 0 001-1V8a1 1 0 00-1-1H8z"/><circle cx="9.5" cy="12" r="1.5"/><circle cx="14.5" cy="12" r="1.5"/><rect x="9" y="16" width="6" height="1.5" rx=".75"/><rect x="2" y="10" width="2" height="4" rx="1"/><rect x="20" y="10" width="2" height="4" rx="1"/></svg></div>`;

function ts(){ const d=new Date(),h=d.getHours(),m=String(d.getMinutes()).padStart(2,'0'); return `${h>=12?'오후':'오전'} ${h>12?h-12:h||12}:${m}`; }

function newChat(){
    closeSidebar();
    resetLoadingUI();
    currentThreadId = null;
    const store = loadStore();
    store.activeId = null;
    saveStore(store);
    document.getElementById('chatContainer').innerHTML = `<div id="welcomeSection"><div class="msg-wrapper"><div class="msg-row">${AI_AVATAR}<div class="ai-bubble-dark">안녕하세요! 주식 초보자를 위한 맞춤형 조언을 드리는 <strong>주식 멘토 AI</strong>입니다. 무엇을 도와드릴까요?</div></div><div class="msg-ts" style="margin-left:48px;">AI Assistant · Just now</div></div><div style="display:flex;flex-direction:column;align-items:center;margin-top:40px;"><div style="font-size:13px;color:#9ca3af;margin-bottom:16px;">아래 질문을 눌러보거나, 직접 입력해보세요</div><div style="display:flex;flex-wrap:wrap;justify-content:center;gap:10px;max-width:520px;"><button class="welcome-btn" onclick="askQuestion('애플 시가총액 알려줘')">애플 시가총액</button><button class="welcome-btn" onclick="askQuestion('테슬라 오늘 뉴스')">테슬라 오늘 뉴스</button><button class="welcome-btn" onclick="askQuestion('PER이 뭐야?')">PER이란?</button><button class="welcome-btn" onclick="askQuestion('엔비디아 분석해줘')">엔비디아 분석</button><button class="welcome-btn" onclick="askQuestion('공매도 위험성 알려줘')">공매도 위험성</button><button class="welcome-btn" onclick="askQuestion('24살이고 연봉 3200인데 투자 전략 알려줘')">연봉 3200 투자 전략</button></div></div></div>`;
    document.getElementById('suggestionChips').style.display='none';
    glossaryHintShown=false;
    renderSidebar();
}

function askQuestion(q){document.getElementById('questionInput').value=q;sendQuestion();}

function handleSendClick(){ if(isLoading) stopGeneration(); else sendQuestion(); }

function setButtonMode(mode){
    const btn=document.getElementById('sendBtn');
    if(mode==='stop'){ btn.innerHTML=STOP_ICON; btn.classList.add('stop'); btn.disabled=false; }
    else { btn.innerHTML=SEND_ICON; btn.classList.remove('stop'); btn.disabled=false; }
}

function stopGeneration(){
    if(abortController){ abortController.abort(); abortController=null; }
    if(currentLoadingId){ removeMessage(currentLoadingId); currentLoadingId=null; }
    // 스트리밍 카드도 정리
    const streamText = document.getElementById('stream-text');
    if(streamText){ const wrapper = streamText.closest('.msg-wrapper'); if(wrapper) wrapper.remove(); }
    isLoading=false; setButtonMode('send');
}

async function sendQuestion(){
    const input=document.getElementById('questionInput');
    const q=input.value.trim(); if(!q||isLoading) return;
    if(q.length>500){ addErrorMessage('질문이 너무 깁니다. 500자 이내로 입력해 주세요.'); return; }
    const w=document.getElementById('welcomeSection');
    if(w){w.remove();document.getElementById('suggestionChips').style.display='flex';}

    if (!currentThreadId) {
        currentThreadId = createConversation();
    }
    const reqThreadId = currentThreadId;

    addMessageToStore(reqThreadId, { role: 'user', content: q, timestamp: Date.now() });
    renderSidebar();

    addUserMessage(q); input.value=''; input.focus();
    isLoading=true; setButtonMode('stop');
    currentLoadingId=addLoadingMessage();
    abortController=new AbortController();
    const timeoutId=setTimeout(()=>abortController.abort(),90000);

    let streamRoute = null;
    let fullText = '';
    let receivedDone = false;
    let cardEl = null;    // 스트리밍 카드 DOM
    let insightEl = null; // 텍스트 영역

    try {
        const r = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({question: q, thread_id: reqThreadId}),
            signal: abortController.signal
        });
        clearTimeout(timeoutId);
        if (!r.ok) throw new Error('서버 오류가 발생했습니다. ('+r.status+')');

        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const {done, value} = await reader.read();
            if (done) break;
            if (currentThreadId !== reqThreadId) break;

            buffer += decoder.decode(value, {stream: true});
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            let eventType = null;
            for (const line of lines) {
                if (line.startsWith('event: ')) {
                    eventType = line.slice(7).trim();
                } else if (line.startsWith('data: ') && eventType) {
                    let payload;
                    try { payload = JSON.parse(line.slice(6)); } catch(e) { continue; }

                    if (eventType === 'meta') {
                        streamRoute = payload.route;
                        // 로딩 말풍선은 유지 — 카드는 아직 만들지 않음

                    } else if (eventType === 'data') {
                        // company 주가 데이터 도착 → 로딩 제거, 카드 생성 + 주가 표시
                        if (currentLoadingId) { removeMessage(currentLoadingId); currentLoadingId = null; }
                        if (!cardEl) {
                            cardEl = addStreamCard(streamRoute);
                            insightEl = cardEl.querySelector('#stream-text');
                        }
                        const topEl = cardEl.querySelector('#stream-data-top');
                        if (topEl) topEl.innerHTML = renderPriceSection(payload);
                        const container = document.getElementById('chatContainer');
                        container.scrollTop = container.scrollHeight;

                    } else if (eventType === 'chunk') {
                        // 첫 chunk에서 카드가 아직 없으면 (비-company 라우트) 생성
                        if (!cardEl) {
                            if (currentLoadingId) { removeMessage(currentLoadingId); currentLoadingId = null; }
                            cardEl = addStreamCard(streamRoute);
                            insightEl = cardEl.querySelector('#stream-text');
                        }
                        if (insightEl && payload.text) {
                            const sl = document.getElementById('stream-loading');
                            if (sl) sl.remove();
                            fullText += payload.text;
                            renderStreamText(insightEl, fullText, streamRoute);
                        }

                    } else if (eventType === 'done') {
                        receivedDone = true;
                        if (currentLoadingId) { removeMessage(currentLoadingId); currentLoadingId = null; }
                        const r = streamRoute || 'general';
                        if (cardEl) {
                            finalizeStreamCard(cardEl, payload, r);
                        } else if (r === 'glossary' && payload.glossary) {
                            // glossary: 카드 생성 후 타이핑 애니메이션
                            cardEl = addStreamCard(r);
                            insightEl = cardEl.querySelector('#stream-text');
                            const sl = document.getElementById('stream-loading');
                            if (sl) sl.remove();
                            typewriteFinalize(cardEl, insightEl, payload, r);
                        } else {
                            addBotResponse(payload, r);
                        }
                        // localStorage 저장
                        const serverThreadId = payload.thread_id || reqThreadId;
                        addMessageToStore(serverThreadId, { role: 'assistant', data: payload, route: r, timestamp: Date.now() });
                        renderSidebar();

                    } else if (eventType === 'error') {
                        if (currentLoadingId) { removeMessage(currentLoadingId); currentLoadingId = null; }
                        if (cardEl) { const wrapper = cardEl.closest('.msg-wrapper'); if (wrapper) wrapper.remove(); }
                        addErrorMessage(payload.message || '응답 생성 중 오류가 발생했습니다.');
                    }
                    eventType = null;
                }
            }
        }
        // 스트림 종료 후 done 없이 끝난 경우
        if (!receivedDone && currentThreadId === reqThreadId) {
            if (cardEl) { const wrapper = cardEl.closest('.msg-wrapper'); if (wrapper) wrapper.remove(); }
            if (currentLoadingId) { removeMessage(currentLoadingId); currentLoadingId = null; }
            addErrorMessage('응답 생성 중 연결이 끊어졌습니다. 다시 시도해 주세요.');
        }
    } catch(e){
        clearTimeout(timeoutId);
        if(e.name==='AbortError') return;
        if(currentThreadId === reqThreadId){
            if (cardEl) { const wrapper = cardEl.closest('.msg-wrapper'); if (wrapper) wrapper.remove(); }
            if(currentLoadingId){ removeMessage(currentLoadingId); currentLoadingId=null; }
            const isNetworkErr = e instanceof TypeError || !e.message || e.message.includes('fetch');
            addErrorMessage(isNetworkErr ? '일시적으로 연결이 불안정합니다. 잠시 후 다시 시도해 주세요.' : e.message);
        }
    } finally {
        if(currentThreadId === reqThreadId){
            isLoading=false; abortController=null; currentLoadingId=null; setButtonMode('send');
        }
    }
}

// ── SSE 스트리밍 헬퍼 ──

function addStreamCard(route) {
    const c = document.getElementById('chatContainer');
    const d = document.createElement('div');
    d.className = 'msg-wrapper fade-in';

    let innerHtml = '';
    const loadingText = (route === 'company') ? '분석 중' : '정보 찾는 중';
    const loadingSpan = `<span id="stream-loading" style="color:#9ca3af;font-size:13px">${loadingText}<span class="stream-loading-dot"></span></span>`;

    // 상단: 주가/지표 등 구조화 데이터 영역
    innerHtml += `<div id="stream-data-top"></div>`;

    if (route === 'company' || route === 'news') {
        innerHtml += `<div class="resp-section"><div class="insight-box"><div class="insight-label">핵심 요약</div><div class="insight-text" id="stream-text">${loadingSpan}</div></div></div>`;
    } else if (route === 'glossary') {
        innerHtml += `<div class="resp-section"><div class="resp-label">용어 설명</div><div class="resp-text" id="stream-text">${loadingSpan}</div></div>`;
    } else {
        innerHtml += `<div class="resp-section"><div class="resp-text" id="stream-text">${loadingSpan}</div></div>`;
    }

    // 하단: follow-up, sources 등 영역
    innerHtml += `<div id="stream-data-bottom"></div>`;

    d.innerHTML = `<div class="msg-row">${AI_AVATAR}<div style="flex:1;min-width:0"><div class="ai-card">${innerHtml}</div><div class="msg-ts" style="margin-top:4px">AI Assistant · ${ts()}</div></div></div>`;
    c.appendChild(d);
    c.scrollTop = c.scrollHeight;
    return d.querySelector('.ai-card');
}

function renderStreamText(el, fullText, route) {
    let display = fullText.replace(/(?:follow_up|후속질문)\s*[:：].*/gi, '').replace(/(?:company_intro|회사소개)\s*[:：].*/gi, '').trimEnd();
    el.textContent = display;
    const container = document.getElementById('chatContainer');
    container.scrollTop = container.scrollHeight;
}

function finalizeStreamCard(cardEl, data, route) {
    const sl = document.getElementById('stream-loading');
    if (sl) sl.remove();

    const topEl = cardEl.querySelector('#stream-data-top');
    const bottomEl = cardEl.querySelector('#stream-data-bottom');
    const textEl = cardEl.querySelector('#stream-text');

    // ── 상단: 주가 데이터 + 핵심 지표 (company/news 라우트) ──
    let topHtml = '';
    if (route === 'company' && data.price) topHtml += `<div style="font-size:11px;color:#9ca3af;margin-bottom:12px">주가 데이터는 15~20분 지연될 수 있습니다.</div>`;

    if (data.ticker_info || data.price) {
        topHtml += `<div class="resp-section">`;
        if (data.ticker_info) topHtml += `<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span style="font-size:17px;font-weight:700;color:#1f2937">${esc(data.ticker_info.company_name)}</span><span style="font-size:13px;color:#6b7280">${esc(data.ticker_info.ticker)}</span></div>`;
        if (data.price) {
            const cp=data.price.current_price, chg=data.price.change??0, chgPct=data.price.change_percent??0;
            const up=chg>=0, clr=up?'#059669':'#dc2626', arr=up?'▲':'▼';
            let pd='-';
            if(cp!=null){
                if(data.price.currency==='KRW') pd=`${Math.round(cp).toLocaleString()}원`;
                else if(data.price.krw_price) pd=`${Math.round(data.price.krw_price).toLocaleString()}원 <span style="font-size:14px;color:#6b7280">($${cp.toLocaleString()})</span>`;
                else pd=`$${cp.toLocaleString()}`;
            }
            topHtml += `<div style="display:flex;align-items:baseline;gap:8px;margin-top:6px;flex-wrap:wrap"><span style="font-size:24px;font-weight:700;color:#1f2937">${pd}</span><span style="color:${clr};font-weight:600;font-size:14px">${arr} ${Math.abs(chgPct).toFixed(2)}%</span></div>`;
            if(data.price.market_cap||data.price.market_cap_tier){
                let capHtml='';
                if(data.price.market_cap) capHtml+=`<span style="font-size:13px;color:#6b7280">시가총액 ${esc(data.price.market_cap)}</span>`;
                if(data.price.market_cap_tier) capHtml+=`<span style="padding:1px 6px;background:#f3f4f6;border-radius:4px;font-size:11px;color:#6b7280;margin-left:6px">${esc(data.price.market_cap_tier)}</span>`;
                topHtml+=`<div style="margin-top:4px">${capHtml}</div>`;
            }
        }
        topHtml += `</div>`;
    }

    if (Array.isArray(data.key_metrics) && data.key_metrics.length) {
        const items=data.key_metrics.map(m=>{
            const lc=m.level==='높음'?'#dc2626':m.level==='낮음'?'#059669':'#6b7280';
            return `<span style="font-size:13px;color:#6b7280">${esc(m.name)} ${esc(m.value)}</span><span style="font-size:12px;color:${lc};margin-left:2px">${esc(m.level)}</span>`;
        }).join('<span style="color:#e5e7eb;margin:0 8px">|</span>');
        topHtml += `<div class="resp-section" style="padding:8px 0">${items}</div>`;
    }

    if (topEl) topEl.innerHTML = topHtml;

    // ── 텍스트 영역: 최종 텍스트로 갱신 + highlightTerms 적용 ──
    if (textEl) {
        let finalText = data.insight || data.glossary || '';
        if (finalText) {
            textEl.innerHTML = highlightTerms((route === 'glossary') ? fmtSent(finalText) : renderMd(finalText));
        } else if (textEl.innerHTML) {
            textEl.innerHTML = highlightTerms(textEl.innerHTML);
        }
    }

    // ── 하단: 뉴스, 회사소개, 면책, 출처, 후속질문 ──
    let bottomHtml = '';

    // 뉴스 카드 (news 라우트)
    if (Array.isArray(data.news) && data.news.length && route === 'news') {
        const nc = data.news.map(n => `<div class="news-card"><a href="${esc(n.url)}" target="_blank" class="news-title">${esc(n.title)}</a><div class="news-meta">${esc(n.source)}${n.published_at?' · '+esc(n.published_at):''}</div>${n.summary?`<div class="news-summary">${esc(n.summary)}</div>`:''}</div>`).join('');
        bottomHtml += `<div class="resp-section"><div class="resp-label">최근 뉴스</div>${nc}</div>`;
    }

    // 회사 소개
    if (data.company_intro) bottomHtml += `<details class="resp-section"><summary style="display:flex;align-items:center;gap:6px;font-size:13px;font-weight:500;color:#4b5563;cursor:pointer;user-select:none"><span class="details-arrow">▶</span>회사 소개</summary><div style="margin-top:8px" class="resp-text">${fmtSent(data.company_intro)}</div></details>`;

    // 면책 문구
    if (route === 'advisor' || route === 'general') bottomHtml += `<div style="font-size:13px;color:#003fb1;margin-bottom:16px">참고용 안내이며, 실제 투자는 본인의 판단으로 결정해 주세요.</div>`;

    // 출처
    if (Array.isArray(data.sources) && data.sources.filter(s=>s&&s.startsWith('http')).length) {
        const validSources = data.sources.filter(s=>s&&s.startsWith('http'));
        const sl = validSources.map(s=>{try{return `<a href="${esc(s)}" target="_blank" style="font-size:12px;color:#6b7280;text-decoration:underline">${esc(new URL(s).hostname.replace('www.',''))}</a>`}catch(e){return ''}}).filter(Boolean);
        if (sl.length) bottomHtml += `<div style="margin-top:12px;padding-top:8px;border-top:1px solid #f3f4f6;font-size:11px;color:#9ca3af">출처: ${sl.join(' · ')}</div>`;
    }

    // 후속 질문
    if (Array.isArray(data.follow_up) && data.follow_up.length) {
        bottomHtml += `<div class="followup-chips">${data.follow_up.map(q=>`<button class="followup-chip" onclick="askQuestion('${esc(q)}')">${esc(q)}</button>`).join('')}</div>`;
    }

    if (bottomEl) bottomEl.innerHTML = bottomHtml;

    // 용어 힌트
    if (!glossaryHintShown && cardEl.innerHTML.includes('term-tooltip')) {
        const hintHtml = `<div style="display:flex;align-items:center;gap:6px;font-size:11px;color:#9ca3af;margin-bottom:12px"><svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>밑줄 친 용어를 클릭하면 뜻을 볼 수 있어요</div>`;
        cardEl.insertAdjacentHTML('afterbegin', hintHtml);
        glossaryHintShown = true;
    }

    // 스크롤
    const container = document.getElementById('chatContainer');
    container.scrollTop = container.scrollHeight;
}

function renderPriceSection(data) {
    let h = '';
    if (data.price) h += `<div style="font-size:11px;color:#9ca3af;margin-bottom:12px">주가 데이터는 15~20분 지연될 수 있습니다.</div>`;

    if (data.ticker_info || data.price) {
        h += `<div class="resp-section">`;
        if (data.ticker_info) h += `<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span style="font-size:17px;font-weight:700;color:#1f2937">${esc(data.ticker_info.company_name)}</span><span style="font-size:13px;color:#6b7280">${esc(data.ticker_info.ticker)}</span></div>`;
        if (data.price) {
            const cp=data.price.current_price, chg=data.price.change??0, chgPct=data.price.change_percent??0;
            const up=chg>=0, clr=up?'#059669':'#dc2626', arr=up?'▲':'▼';
            let pd='-';
            if(cp!=null){
                if(data.price.currency==='KRW') pd=`${Math.round(cp).toLocaleString()}원`;
                else if(data.price.krw_price) pd=`${Math.round(data.price.krw_price).toLocaleString()}원 <span style="font-size:14px;color:#6b7280">($${cp.toLocaleString()})</span>`;
                else pd=`$${cp.toLocaleString()}`;
            }
            h += `<div style="display:flex;align-items:baseline;gap:8px;margin-top:6px;flex-wrap:wrap"><span style="font-size:24px;font-weight:700;color:#1f2937">${pd}</span><span style="color:${clr};font-weight:600;font-size:14px">${arr} ${Math.abs(chgPct).toFixed(2)}%</span></div>`;
            if(data.price.market_cap||data.price.market_cap_tier){
                let capHtml='';
                if(data.price.market_cap) capHtml+=`<span style="font-size:13px;color:#6b7280">시가총액 ${esc(data.price.market_cap)}</span>`;
                if(data.price.market_cap_tier) capHtml+=`<span style="padding:1px 6px;background:#f3f4f6;border-radius:4px;font-size:11px;color:#6b7280;margin-left:6px">${esc(data.price.market_cap_tier)}</span>`;
                h+=`<div style="margin-top:4px">${capHtml}</div>`;
            }
        }
        h += `</div>`;
    }

    if (Array.isArray(data.key_metrics) && data.key_metrics.length) {
        const items=data.key_metrics.map(m=>{
            const lc=m.level==='높음'?'#dc2626':m.level==='낮음'?'#059669':'#6b7280';
            return `<span style="font-size:13px;color:#6b7280">${esc(m.name)} ${esc(m.value)}</span><span style="font-size:12px;color:${lc};margin-left:2px">${esc(m.level)}</span>`;
        }).join('<span style="color:#e5e7eb;margin:0 8px">|</span>');
        h += `<div class="resp-section" style="padding:8px 0">${items}</div>`;
    }
    return h;
}

function typewriteFinalize(cardEl, textEl, data, route) {
    const text = data.glossary || data.insight || '';
    let idx = 0;
    const chunkSize = 3;
    const interval = 20;
    const timer = setInterval(() => {
        idx += chunkSize;
        if (idx >= text.length) {
            idx = text.length;
            clearInterval(timer);
            finalizeStreamCard(cardEl, data, route);
            return;
        }
        textEl.innerHTML = fmtSent(text.substring(0, idx));
        const container = document.getElementById('chatContainer');
        container.scrollTop = container.scrollHeight;
    }, interval);
}


function addUserMessage(text){
    const c=document.getElementById('chatContainer'), d=document.createElement('div');
    d.className='msg-wrapper fade-in';
    d.innerHTML=`<div class="msg-row user"><div class="user-bubble">${escapeHtml(text)}</div></div><div class="msg-ts right">You · ${ts()}</div>`;
    c.appendChild(d); c.scrollTop=c.scrollHeight;
}

const LOADING_MESSAGES=['질문 분석 중','데이터 조회 중','최신 정보 확인 중','답변 정리 중'];
let loadingInterval=null;

function addLoadingMessage(){
    const c=document.getElementById('chatContainer'), id='ld-'+Date.now(), d=document.createElement('div');
    d.id=id; d.className='msg-wrapper fade-in';
    d.innerHTML=`<div class="msg-row">${AI_AVATAR}<div><div class="ai-bubble-dark" style="color:#6b7280;font-size:13px"><span id="loading-text">${LOADING_MESSAGES[0]}</span><span class="stream-loading-dot"></span></div></div></div>`;
    c.appendChild(d); c.scrollTop=c.scrollHeight;
    let idx=0;
    loadingInterval=setInterval(()=>{
        idx=(idx+1)%LOADING_MESSAGES.length;
        const s=document.getElementById('loading-text'); if(!s)return;
        s.style.opacity='0'; setTimeout(()=>{s.textContent=LOADING_MESSAGES[idx];s.style.opacity='1';},250);
    },1800);
    return id;
}

function removeMessage(id){ if(loadingInterval){clearInterval(loadingInterval);loadingInterval=null;} const e=document.getElementById(id); if(e)e.remove(); }

function addErrorMessage(text){
    const c=document.getElementById('chatContainer'), d=document.createElement('div');
    d.className='msg-wrapper fade-in';
    d.innerHTML=`<div class="msg-row">${AI_AVATAR}<div><div class="ai-bubble-dark">${escapeHtml(text)}</div><div class="msg-ts" style="margin-top:4px">AI Assistant · ${ts()}</div></div></div>`;
    c.appendChild(d); c.scrollTop=c.scrollHeight;
}

function addBotResponse(data,route){
    const c=document.getElementById('chatContainer'), d=document.createElement('div');
    d.className='msg-wrapper fade-in';
    let rhtml;
    try { rhtml=renderResponse(data,route); } catch(e) {
        console.error('renderResponse 오류:', e);
        rhtml=`<div class="resp-text">${escapeHtml(data.insight||data.glossary||'응답을 표시하는 중 오류가 발생했습니다.')}</div>`;
    }
    let hint='';
    if(!glossaryHintShown&&rhtml.includes('term-tooltip')){
        hint=`<div style="display:flex;align-items:center;gap:6px;font-size:11px;color:#9ca3af;margin-bottom:12px"><svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>밑줄 친 용어를 클릭하면 뜻을 볼 수 있어요</div>`;
        glossaryHintShown=true;
    }
    d.innerHTML=`<div class="msg-row">${AI_AVATAR}<div style="flex:1;min-width:0"><div class="ai-card">${hint}${rhtml}</div><div class="msg-ts" style="margin-top:4px">AI Assistant · ${ts()}</div></div></div>`;
    c.appendChild(d); c.scrollTop=c.scrollHeight;
}

function renderResponse(data,route){
    let h='';
    if(route==='company'&&data.price) h+=`<div style="font-size:11px;color:#9ca3af;margin-bottom:12px">주가 데이터는 15~20분 지연될 수 있습니다.</div>`;

    // 회사명 + 현재가 + 등락률 + 시가총액 등급
    if(data.ticker_info||data.price){
        h+=`<div class="resp-section">`;
        if(data.ticker_info) h+=`<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap"><span style="font-size:17px;font-weight:700;color:#1f2937">${esc(data.ticker_info.company_name)}</span><span style="font-size:13px;color:#6b7280">${esc(data.ticker_info.ticker)}</span></div>`;
        if(data.price){
            const cp=data.price.current_price, chg=data.price.change??0, chgPct=data.price.change_percent??0;
            const up=chg>=0, clr=up?'#059669':'#dc2626', arr=up?'▲':'▼';
            let pd='-';
            if(cp!=null){
                if(data.price.currency==='KRW') pd=`${Math.round(cp).toLocaleString()}원`;
                else if(data.price.krw_price) pd=`${Math.round(data.price.krw_price).toLocaleString()}원 <span style="font-size:14px;color:#6b7280">($${cp.toLocaleString()})</span>`;
                else pd=`$${cp.toLocaleString()}`;
            }
            h+=`<div style="display:flex;align-items:baseline;gap:8px;margin-top:6px;flex-wrap:wrap"><span style="font-size:24px;font-weight:700;color:#1f2937">${pd}</span><span style="color:${clr};font-weight:600;font-size:14px">${arr} ${Math.abs(chgPct).toFixed(2)}%</span></div>`;
            if(data.price.market_cap||data.price.market_cap_tier){
                let capHtml='';
                if(data.price.market_cap) capHtml+=`<span style="font-size:13px;color:#6b7280">시가총액 ${esc(data.price.market_cap)}</span>`;
                if(data.price.market_cap_tier) capHtml+=`<span style="padding:1px 6px;background:#f3f4f6;border-radius:4px;font-size:11px;color:#6b7280;margin-left:6px">${esc(data.price.market_cap_tier)}</span>`;
                h+=`<div style="margin-top:4px">${capHtml}</div>`;
            }
        }
        h+=`</div>`;
    }

    // 핵심 지표
    if(Array.isArray(data.key_metrics)&&data.key_metrics.length){
        const items=data.key_metrics.map(m=>{
            const lc=m.level==='높음'?'#dc2626':m.level==='낮음'?'#059669':'#6b7280';
            return `<span style="font-size:13px;color:#6b7280">${esc(m.name)} ${esc(m.value)}</span><span style="font-size:12px;color:${lc};margin-left:2px">${esc(m.level)}</span>`;
        }).join('<span style="color:#e5e7eb;margin:0 8px">|</span>');
        h+=`<div class="resp-section" style="padding:8px 0">${items}</div>`;
    }

    // 핵심 요약 (company/news 라우트)
    if(data.insight&&(route==='company'||route==='news'))
        h+=`<div class="resp-section"><div class="insight-box"><div class="insight-label">핵심 요약</div><div class="insight-text">${renderMd(data.insight)}</div></div></div>`;

    // 뉴스 (news 라우트에서만 표시)
    if(Array.isArray(data.news)&&data.news.length&&route==='news'){
        const nc=data.news.map(n=>`<div class="news-card"><a href="${esc(n.url)}" target="_blank" class="news-title">${esc(n.title)}</a><div class="news-meta">${esc(n.source)}${n.published_at?' · '+esc(n.published_at):''}</div>${n.summary?`<div class="news-summary">${esc(n.summary)}</div>`:''}</div>`).join('');
        h+=`<div class="resp-section"><div class="resp-label">최근 뉴스</div>${nc}</div>`;
    }

    // 회사 소개 (접이식)
    if(data.company_intro) h+=`<details class="resp-section"><summary style="display:flex;align-items:center;gap:6px;font-size:13px;font-weight:500;color:#4b5563;cursor:pointer;user-select:none"><span class="details-arrow">▶</span>회사 소개</summary><div style="margin-top:8px" class="resp-text">${fmtSent(data.company_intro)}</div></details>`;

    // 용어 설명
    if(data.glossary) h+=`<div class="resp-section"><div class="resp-label">용어 설명</div><div class="resp-text">${fmtSent(data.glossary)}</div></div>`;

    // 일반/어드바이저 라우트의 insight
    if(data.insight&&route!=='company'&&route!=='news') h+=`<div class="resp-section"><div class="resp-text">${renderMd(data.insight)}</div></div>`;

    if(route==='advisor'||route==='general') h+=`<div style="font-size:13px;color:#003fb1;margin-bottom:16px">참고용 안내이며, 실제 투자는 본인의 판단으로 결정해 주세요.</div>`;

    // 출처 (유효한 URL이 있을 때만 표시)
    if(Array.isArray(data.sources)&&data.sources.filter(s=>s&&s.startsWith('http')).length){
        const validSources=data.sources.filter(s=>s&&s.startsWith('http'));
        const sl=validSources.map(s=>{try{return `<a href="${esc(s)}" target="_blank" style="font-size:12px;color:#6b7280;text-decoration:underline">${esc(new URL(s).hostname.replace('www.',''))}</a>`}catch(e){return ''}}).filter(Boolean);
        if(sl.length) h+=`<div style="margin-top:12px;padding-top:8px;border-top:1px solid #f3f4f6;font-size:11px;color:#9ca3af">출처: ${sl.join(' · ')}</div>`;
    }

    // 후속 질문 버튼
    if(Array.isArray(data.follow_up)&&data.follow_up.length){
        h+=`<div class="followup-chips">${data.follow_up.map(q=>`<button class="followup-chip" onclick="askQuestion('${esc(q)}')">${esc(q)}</button>`).join('')}</div>`;
    }
    return highlightTerms(h);
}

function esc(t){return escapeHtml(t);}
function escapeHtml(t){if(!t)return '';const m={'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'};return String(t).replace(/[&<>"']/g,c=>m[c]);}
function fmtSent(t){if(!t)return '';const e=escapeHtml(t);if(e.includes('\n'))return e.split('\n').filter(s=>s.trim()).map(s=>`<p style="margin-bottom:6px">${s.trim()}</p>`).join('');return e.split(/(?<=[.다])\s+/).filter(s=>s.trim()).map(s=>`<p style="margin-bottom:6px">${s.trim()}</p>`).join('');}
function renderMd(t){if(!t)return '';return escapeHtml(t).split('\n').filter(s=>s.trim()).map(l=>{let p=l.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');p=p.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,'<a href="$2" target="_blank" style="text-decoration:underline">$1</a>');return `<p style="margin-bottom:6px">${p}</p>`;}).join('');}
