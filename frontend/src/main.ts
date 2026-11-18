import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import { registerUiComponents } from './components/ui/register'
import './styles/theme.css'
import './styles/app.css'

const app = createApp(App)
registerUiComponents(app)
app.use(createPinia()).use(router).mount('#app')
