// 남길 때 알림만 받는다(운전자 정보는 오지 않는다). 누르면 그 순간을 고른 채로 연다.
// 첫 화면 파일은 폰에 담아 둔다. 새 파일을 먼저 받고(고친 화면이 바로 보이게), 무료 서버가 잠들어 4초 안에 못 받거나
// 인터넷이 끊기면 담아 둔 화면을 띄운다(불러오는 중·다시 시도). 받은 새 파일은 다음을 위해 담아 둔다
const SHELL = "dodam-shell-5";
self.addEventListener("install", () => self.skipWaiting());
// 옛 이름으로 담아 둔 화면은 지운다
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k.startsWith("dodam-shell-") && k !== SHELL).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.origin !== location.origin || e.request.mode !== "navigate" || (u.pathname !== "/" && u.pathname !== "/index.html")) return;
  e.respondWith(caches.open(SHELL).then(async c => {
    const net = fetch(e.request).then(r => { if (r.ok) c.put("/", r.clone()); return r; });
    e.waitUntil(net.catch(() => {}));
    const hit = await c.match("/");
    if (!hit) return net;
    const late = new Promise(ok => setTimeout(() => ok(hit), 4000));
    return Promise.race([net.then(r => r.ok ? r : hit, () => hit), late]);   // 서버가 깨는 중(503)이어도 담아 둔 화면
  }));
});
self.addEventListener("push", e => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch (err) {}
  e.waitUntil(self.registration.showNotification(d.title || "도담도담", {
    // badge: 안드로이드 상태 표시줄 작은 아이콘(투명 바탕 흰 말풍선)
    body: d.body || "", icon: "/icon-192.png", badge: "/badge-96.png", tag: d.tag || "dodam", data: { url: d.url || "/" }
  }));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || "/";
  e.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
    // 열린 창은 주소를 옮기지 않고 앞으로 가져온 뒤 알려 준다: 마무리 중이던 녹음이 사라지지 않게(창이 알아서 연다)
    for (const c of list) { if ("focus" in c) { c.postMessage({ type: "open", url }); return c.focus(); } }
    return clients.openWindow(url);
  }));
});
