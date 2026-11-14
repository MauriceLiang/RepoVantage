import { createApp } from 'vue'
import ComponentGalleryPage from './pages/ComponentGalleryPage.vue'
import { registerUiComponents } from './components/ui/register'
import './styles.css'

const app = createApp(ComponentGalleryPage)
registerUiComponents(app)
app.mount('#component-gallery')
