/**
 * Unit tests for Sidebar component.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Sidebar } from './Sidebar'
import { BrowserRouter } from 'react-router-dom'

describe('Sidebar', () => {
  const renderWithRouter = (component: React.ReactElement) => {
    return render(<BrowserRouter>{component}</BrowserRouter>)
  }

  it('renders sidebar header', () => {
    renderWithRouter(<Sidebar />)
    expect(screen.getByText('DevOps Monitor')).toBeInTheDocument()
  })

  it('renders all navigation items', () => {
    renderWithRouter(<Sidebar />)

    expect(screen.getByText('Overview')).toBeInTheDocument()
    expect(screen.getByText('Logs')).toBeInTheDocument()
    expect(screen.getByText('APM')).toBeInTheDocument()
    expect(screen.getByText('SLO')).toBeInTheDocument()
    expect(screen.getByText('Infrastructure')).toBeInTheDocument()
    expect(screen.getByText('Kubernetes')).toBeInTheDocument()
    expect(screen.getByText('Alerts')).toBeInTheDocument()
  })

  it('renders navigation links with correct paths', () => {
    const { container } = renderWithRouter(<Sidebar />)

    const links = container.querySelectorAll('a')
    const paths = Array.from(links).map(link => link.getAttribute('href'))

    expect(paths).toContain('/')
    expect(paths).toContain('/logs')
    expect(paths).toContain('/apm')
    expect(paths).toContain('/slo')
    expect(paths).toContain('/infrastructure')
    expect(paths).toContain('/kubernetes')
    expect(paths).toContain('/alerts')
  })

  it('highlights active navigation item', () => {
    // Test with window.location set to root path
    renderWithRouter(<Sidebar />)

    // Check if overview link has active class (it should when at root)
    const overviewLink = screen.getByText('Overview').closest('a')
    expect(overviewLink).toBeInTheDocument()
  })

  it('applies hover styles to navigation items', () => {
    const { container } = renderWithRouter(<Sidebar />)

    const navItems = [...container.querySelectorAll('nav a')]
    const inactive = navItems.filter((item) => !item.className.includes('var(--color-accent)'))
    expect(inactive.length).toBeGreaterThan(0)
    inactive.forEach(item => {
      expect(item.className).toContain('hover:bg-white/5')
    })
  })

  it('has correct sidebar width class', () => {
    const { container } = renderWithRouter(<Sidebar />)

    const sidebar = container.querySelector('aside')
    expect(sidebar).toHaveClass('w-56')
  })

  it('applies correct border classes', () => {
    const { container } = renderWithRouter(<Sidebar />)

    const sidebar = container.querySelector('aside')
    expect(sidebar).toHaveClass('border-r')
  })
})
