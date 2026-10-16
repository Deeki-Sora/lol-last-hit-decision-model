/** Optional adapter for a selector website maintained in 2026 or later.
 * Import this file into the selector's own page. It cannot read another site's DOM.
 * No local-workbench authentication token crosses this bridge.
 */
export function connectWorkbench({projectUrl, updatedAt, onConfiguration}) {
  const query = new URLSearchParams(location.search);
  const origin = query.get('workbench_origin'), nonce = query.get('bridge_nonce');
  if (!origin || !nonce || !window.opener) throw Error('Open this page from the workbench');
  const local = new URL(origin);
  if (!['127.0.0.1', 'localhost'].includes(local.hostname) || local.protocol !== 'http:') throw Error('Loopback workbench origin required');
  if (!/^20\d\d-\d\d-\d\d/.test(updatedAt) || Number(updatedAt.slice(0, 4)) < 2026) throw Error('A 2026-or-later provider update is required');
  function receive(event) {
    if (event.origin !== origin || event.source !== window.opener || event.data?.nonce !== nonce) return;
    if (event.data.type === 'lol-workbench.selector.init') onConfiguration(event.data.configuration);
  }
  window.addEventListener('message', receive);
  window.opener.postMessage({type: 'lol-workbench.selector.ready', nonce}, origin);
  return {
    submit(configuration) {
      window.opener.postMessage({type: 'lol-workbench.selector.result', nonce, configuration,
        provider: {project_url: projectUrl, updated_at: updatedAt, data_patch: configuration.match_setup.patch}}, origin);
    },
    disconnect() { window.removeEventListener('message', receive); }
  };
}
