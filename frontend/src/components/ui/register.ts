import type { App } from 'vue'
import UiBadge from './UiBadge.vue'
import UiButton from './UiButton.vue'
import UiInput from './UiInput.vue'
import UiMetricCard from './UiMetricCard.vue'
import UiNavItem from './UiNavItem.vue'
import UiPageHeader from './UiPageHeader.vue'
import UiPanel from './UiPanel.vue'
import UiSelect from './UiSelect.vue'

export function registerUiComponents(app: App) {
  app.component('UiBadge', UiBadge)
  app.component('UiButton', UiButton)
  app.component('UiInput', UiInput)
  app.component('UiMetricCard', UiMetricCard)
  app.component('UiNavItem', UiNavItem)
  app.component('UiPageHeader', UiPageHeader)
  app.component('UiPanel', UiPanel)
  app.component('UiSelect', UiSelect)
}
