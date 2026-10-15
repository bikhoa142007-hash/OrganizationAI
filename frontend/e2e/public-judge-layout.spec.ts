import { expect, test } from '@playwright/test'

test('public Judge input fields stay readable across desktop and mobile widths', async ({ page }, testInfo) => {
  await page.goto('/challenge-a')

  const form = page.locator('.public-judge-input form')
  await expect(form).toBeVisible()

  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 })

    const layout = await form.evaluate(element => {
      const fields = Array.from(element.querySelectorAll('label'))
      const boxes = fields.map(field => {
        const label = field.querySelector('span')
        const control = field.querySelector('input, textarea')
        if (!label || !control) return null

        const fieldBox = field.getBoundingClientRect()
        const labelBox = label.getBoundingClientRect()
        const controlBox = control.getBoundingClientRect()
        return {
          field: { left: fieldBox.left, right: fieldBox.right, top: fieldBox.top, bottom: fieldBox.bottom },
          label: { left: labelBox.left, right: labelBox.right, top: labelBox.top, bottom: labelBox.bottom },
          control: { left: controlBox.left, right: controlBox.right, top: controlBox.top, bottom: controlBox.bottom },
        }
      })

      return {
        display: getComputedStyle(element).display,
        viewportWidth: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        boxes,
      }
    })

    expect(layout.display, `form display at ${width}px`).toBe('grid')
    expect(layout.documentWidth, `page width at ${width}px`).toBeLessThanOrEqual(layout.viewportWidth)
    expect(layout.boxes).toHaveLength(9)

    const boxes = layout.boxes.filter((box): box is NonNullable<typeof box> => box !== null)
    expect(boxes).toHaveLength(9)
    for (const box of boxes) {
      expect(box.control.top, `control follows its label at ${width}px`).toBeGreaterThanOrEqual(box.label.bottom)
      expect(box.control.left, `control stays in its field at ${width}px`).toBeGreaterThanOrEqual(box.field.left)
      expect(box.control.right, `control stays in its field at ${width}px`).toBeLessThanOrEqual(box.field.right)
    }

    const overlaps = boxes.some((box, index) => boxes.slice(index + 1).some(other =>
      box.field.left < other.field.right
      && box.field.right > other.field.left
      && box.field.top < other.field.bottom
      && box.field.bottom > other.field.top
    ))
    expect(overlaps, `form fields do not overlap at ${width}px`).toBe(false)
  }

  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.screenshot({ path: testInfo.outputPath('challenge-a-layout.png'), fullPage: true })
})
