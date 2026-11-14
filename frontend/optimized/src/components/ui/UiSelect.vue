<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Check, ChevronDown, Search } from 'lucide-vue-next'

export interface UiSelectOption {
  value: string
  label: string
}

const props = withDefaults(defineProps<{
  modelValue?: string
  options: UiSelectOption[]
  label: string
  placeholder?: string
  searchable?: boolean
  searchPlaceholder?: string
  disabled?: boolean
}>(), {
  modelValue: '',
  placeholder: '请选择',
  searchable: false,
  searchPlaceholder: '搜索选项',
  disabled: false,
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const root = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)
const open = ref(false)
const query = ref('')
const activeIndex = ref(0)
const id = `ui-select-${Math.random().toString(36).slice(2, 9)}`
const listboxId = `${id}-listbox`
const activeOption = computed(() => filteredOptions.value[activeIndex.value])
const activeOptionId = computed(() => activeOption.value ? `${id}-option-${activeIndex.value}` : undefined)
const selectedOption = computed(() => props.options.find((option) => option.value === props.modelValue))
const filteredOptions = computed(() => {
  const search = query.value.trim().toLocaleLowerCase()
  return search ? props.options.filter((option) => option.label.toLocaleLowerCase().includes(search)) : props.options
})

function focusActiveOption() {
  nextTick(() => {
    if (activeOptionId.value) document.getElementById(activeOptionId.value)?.scrollIntoView({ block: 'nearest' })
  })
}

function openMenu() {
  if (props.disabled) return
  query.value = ''
  open.value = true
  const selectedIndex = props.options.findIndex((option) => option.value === props.modelValue)
  activeIndex.value = Math.max(0, selectedIndex)
  if (props.searchable) nextTick(() => searchInput.value?.focus())
}

function closeMenu(restoreFocus = false) {
  open.value = false
  query.value = ''
  if (restoreFocus) nextTick(() => trigger.value?.focus())
}

function chooseOption(option: UiSelectOption) {
  emit('update:modelValue', option.value)
  closeMenu(true)
}

function onKeydown(event: KeyboardEvent) {
  if (!open.value) {
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) {
      event.preventDefault()
      openMenu()
    }
    return
  }

  if (event.key === 'Escape') {
    event.preventDefault()
    closeMenu(true)
  } else if (event.key === 'ArrowDown' && filteredOptions.value.length) {
    event.preventDefault()
    activeIndex.value = (activeIndex.value + 1) % filteredOptions.value.length
    focusActiveOption()
  } else if (event.key === 'ArrowUp' && filteredOptions.value.length) {
    event.preventDefault()
    activeIndex.value = (activeIndex.value - 1 + filteredOptions.value.length) % filteredOptions.value.length
    focusActiveOption()
  } else if (event.key === 'Home' && filteredOptions.value.length) {
    event.preventDefault()
    activeIndex.value = 0
    focusActiveOption()
  } else if (event.key === 'End' && filteredOptions.value.length) {
    event.preventDefault()
    activeIndex.value = filteredOptions.value.length - 1
    focusActiveOption()
  } else if (event.key === 'Enter' && activeOption.value) {
    event.preventDefault()
    chooseOption(activeOption.value)
  } else if (event.key === 'Tab') {
    closeMenu()
  }
}

function onQueryInput() {
  activeIndex.value = 0
}

function onOutsidePointer(event: PointerEvent) {
  if (event.target instanceof Node && !root.value?.contains(event.target)) closeMenu()
}

onMounted(() => document.addEventListener('pointerdown', onOutsidePointer))
onBeforeUnmount(() => document.removeEventListener('pointerdown', onOutsidePointer))
</script>

<template>
  <div ref="root" class="ui-select">
    <button
      ref="trigger"
      class="ui-select__trigger"
      type="button"
      role="combobox"
      aria-haspopup="listbox"
      :aria-label="label"
      :aria-expanded="open"
      :aria-controls="listboxId"
      :aria-activedescendant="open ? activeOptionId : undefined"
      :disabled="disabled"
      @click="open ? closeMenu() : openMenu()"
      @keydown="onKeydown"
    >
      <span :class="['ui-select__value', { 'ui-select__value--placeholder': !selectedOption }]">{{ selectedOption?.label || placeholder }}</span>
      <ChevronDown :size="14" class="ui-select__chevron" :class="{ 'ui-select__chevron--open': open }" aria-hidden="true" />
    </button>

    <Transition name="select-menu">
      <div v-if="open" class="ui-select__menu" @keydown="onKeydown">
        <label v-if="searchable" class="ui-select__search">
          <Search :size="13" aria-hidden="true" />
          <input ref="searchInput" v-model="query" type="search" :aria-label="`${label}搜索`" :placeholder="searchPlaceholder" @input="onQueryInput" />
        </label>
        <div :id="listboxId" class="ui-select__options" role="listbox" :aria-label="label">
          <div v-for="(option, index) in filteredOptions" :id="`${id}-option-${index}`" :key="option.value" class="ui-select__option" :class="{ 'ui-select__option--active': index === activeIndex }" role="option" :aria-selected="option.value === modelValue" @mouseenter="activeIndex = index" @click="chooseOption(option)">
            <span>{{ option.label }}</span>
            <Transition name="select-check"><Check v-if="option.value === modelValue" :size="13" aria-hidden="true" /></Transition>
          </div>
          <p v-if="!filteredOptions.length" class="ui-select__empty">没有匹配选项</p>
        </div>
      </div>
    </Transition>
  </div>
</template>
