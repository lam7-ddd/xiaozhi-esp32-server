import ElementUI from 'element-ui';
import 'element-ui/lib/theme-chalk/index.css';
import 'normalize.css/normalize.css'; // A modern alternative to CSS resets
import Vue from 'vue';
import App from './App.vue';
import router from './router';
import store from './store';
import './styles/global.scss';
import { register as registerServiceWorker } from './registerServiceWorker';

Vue.use(ElementUI);

Vue.config.productionTip = false

// Service Workerを登録
registerServiceWorker();

// Vueインスタンスを作成
new Vue({
  router,
  store,
  render: function (h) { return h(App) }
}).$mount('#app')
