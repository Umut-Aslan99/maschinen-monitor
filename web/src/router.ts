import { createRouter, createWebHistory } from 'vue-router';

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./pages/Hall.vue'), meta: { title: 'Halle' } },
    { path: '/maschine/:id', component: () => import('./pages/Machine.vue'), props: true, meta: { title: 'Maschine' } },
    { path: '/stillstaende', component: () => import('./pages/Downtime.vue'), meta: { title: 'Stillstände' } },
    { path: '/alarme', component: () => import('./pages/Alarms.vue'), meta: { title: 'Alarme' } },
    { path: '/:rest(.*)*', redirect: '/' },
  ],
  scrollBehavior: () => ({ top: 0 }),
});

router.afterEach((to) => {
  const page = to.params.id ? String(to.params.id) : String(to.meta.title ?? '');
  document.title = `${page} · Maschinen-Monitor`;
});
