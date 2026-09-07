<template>
  <router-view />
  <!-- 全局版本号页脚：所有页面右下角常驻，不拦截点击 -->
  <div class="app-version" :title="VERSION_TITLE">{{ VERSION_TEXT }}</div>
</template>

<script setup>
// 根组件：仅承载路由出口 + 全局版本号
import { VERSION_TEXT, VERSION_TITLE } from './version.js'
</script>
