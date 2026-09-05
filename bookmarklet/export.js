/* Claude chat exporter.
   Run from a claude.ai tab: paste into the DevTools console, or install as a
   bookmarklet (see README). Uses your existing browser login and the same
   internal API the web app uses, so it works on any plan.

   Downloads a JSON file that export_chats.py understands.

   Modes:  window.__CLAUDE_EXPORT_MODE = 'all'      (default) every conversation
           window.__CLAUDE_EXPORT_MODE = 'current'  only the open conversation
   Override org: window.__CLAUDE_EXPORT_ORG = '<org uuid>' */
(async () => {
  const MODE = window.__CLAUDE_EXPORT_MODE || 'all';
  const CONCURRENCY = 3;
  const PAGE_SIZE = 100;
  const DELAY_MS = 150;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const api = async (path, attempt = 0) => {
    const res = await fetch(path, { credentials: 'include', headers: { accept: 'application/json' } });
    if ((res.status === 429 || res.status >= 500) && attempt < 5) {
      await sleep(1000 * 2 ** attempt);
      return api(path, attempt + 1);
    }
    if (!res.ok) throw new Error(res.status + ' ' + res.statusText + ' for ' + path);
    return res.json();
  };

  const pickOrg = async () => {
    const orgs = await api('/api/organizations');
    if (!Array.isArray(orgs) || orgs.length === 0) throw new Error('No organizations visible for this account');
    console.log('[export] organizations:', orgs.map((o) => o.uuid + '  ' + o.name));
    const override = window.__CLAUDE_EXPORT_ORG;
    if (override) return orgs.find((o) => o.uuid === override) || { uuid: override, name: '(override)' };
    const cookie = document.cookie.match(/lastActiveOrg=([0-9a-f-]{36})/);
    const active = cookie && orgs.find((o) => o.uuid === cookie[1]);
    const chosen = active || orgs.find((o) => (o.capabilities || []).includes('chat')) || orgs[0];
    console.log('[export] using org:', chosen.uuid, chosen.name);
    return chosen;
  };

  const listConversations = async (orgId) => {
    const seen = new Map();
    for (let offset = 0; ; offset += PAGE_SIZE) {
      const page = await api('/api/organizations/' + orgId + '/chat_conversations?limit=' + PAGE_SIZE + '&offset=' + offset);
      if (!Array.isArray(page)) throw new Error('Unexpected conversation list response');
      let added = 0;
      for (const c of page) {
        if (!seen.has(c.uuid)) { seen.set(c.uuid, c); added += 1; }
      }
      if (page.length < PAGE_SIZE || added === 0) break;
    }
    return [...seen.values()];
  };

  const fetchConversation = (orgId, id) =>
    api('/api/organizations/' + orgId + '/chat_conversations/' + id + '?tree=True&rendering_mode=messages&render_all_tools=true');

  const download = (name, data) => {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { a.remove(); URL.revokeObjectURL(url); }, 1000);
  };

  const stamp = new Date().toISOString().slice(0, 10);
  const org = await pickOrg();

  if (MODE === 'current') {
    const match = location.pathname.match(/\/chat\/([0-9a-f-]{36})/);
    if (!match) throw new Error('Open a conversation first (URL should look like /chat/<uuid>)');
    const convo = await fetchConversation(org.uuid, match[1]);
    download('claude-conversation-' + match[1].slice(0, 8) + '-' + stamp + '.json', [convo]);
    console.log('[export] done: 1 conversation');
    return;
  }

  const summaries = await listConversations(org.uuid);
  console.log('[export] found ' + summaries.length + ' conversations, fetching each...');
  const out = new Array(summaries.length);
  const failed = [];
  let next = 0;
  let done = 0;

  const worker = async () => {
    while (next < summaries.length) {
      const i = next;
      next += 1;
      try {
        out[i] = await fetchConversation(org.uuid, summaries[i].uuid);
      } catch (e) {
        failed.push({ uuid: summaries[i].uuid, name: summaries[i].name, error: String(e) });
        out[i] = summaries[i];
      }
      done += 1;
      if (done % 10 === 0 || done === summaries.length) console.log('[export] ' + done + '/' + summaries.length);
      await sleep(DELAY_MS);
    }
  };

  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  download('claude-conversations-' + stamp + '.json', out);
  console.log('[export] done: ' + (summaries.length - failed.length) + ' ok, ' + failed.length + ' failed', failed);
})().catch((e) => {
  console.error('[export] failed:', e);
  alert('Claude export failed: ' + e.message);
});
