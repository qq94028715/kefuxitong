import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', component: () => import('./views/Login.vue') },
  {
    path: '/admin',
    component: () => import('./views/Admin.vue'),
    meta: { role: 'admin' },
  },
  {
    path: '/train',
    component: () => import('./views/Train.vue'),
    meta: { role: 'agent' },
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach((to) => {
  const role = localStorage.getItem('role')
  if (to.meta.role && to.meta.role !== role) {
    return '/login'
  }
})

export default router
