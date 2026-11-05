import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { Pager } from './backendUi'

afterEach(cleanup)

it.each([['Anterior', 0], ['Siguiente', 100]])('paginar con %s dentro de un formulario no lo envía', (button, offset) => {
  const change = vi.fn()
  const submit = vi.fn((event: React.FormEvent) => event.preventDefault())
  render(<form onSubmit={submit}><Pager offset={50} count={50} loading={false} change={change} /></form>)
  fireEvent.click(screen.getByRole('button', { name: button }))
  expect(change).toHaveBeenCalledExactlyOnceWith(offset)
  expect(submit).not.toHaveBeenCalled()
})
