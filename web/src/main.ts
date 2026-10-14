import { createApp } from 'vue';
import '@fontsource-variable/inter';
import '@fontsource-variable/space-grotesk';
import '@fontsource-variable/jetbrains-mono';
import './styles/app.css';
import App from './App.vue';
import { api } from './api';
import { connect } from './live';
import { meta } from './meta';
import { router } from './router';

// The machine catalog is needed by every page; then the live connection starts.
meta.value = await api.meta().catch(() => meta.value);
connect();
createApp(App).use(router).mount('#app');
