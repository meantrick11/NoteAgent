/**
 * 复制消息原文。用 navigator.clipboard.writeText，拒绝或缺失时返回 false，
 * 由调用方给出可见反馈——复制失败不能静默。
 */
export async function copyMessageText(text: string): Promise<boolean> {
  const clipboard = typeof navigator === 'undefined' ? undefined : navigator.clipboard
  if (!clipboard || typeof clipboard.writeText !== 'function') return false
  try {
    await clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
