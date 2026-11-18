export function positionChartTooltip(host: HTMLElement, tip: HTMLElement, {
  guideX, pointerX = guideX, barBounds, allowBarOverlap, topOffset = 0,
}: {
  guideX: number;
  pointerX?: number;
  barBounds?: { left: number; right: number };
  allowBarOverlap?: boolean;
  topOffset?: number;
}): boolean {
  const chart = host.getBoundingClientRect();
  const content = host.closest<HTMLElement>('#content-scroll');
  const contentBounds = content?.getBoundingClientRect();
  const contentLeft = (contentBounds?.left ?? 0) + (content?.clientLeft ?? 0);
  const contentTop = (contentBounds?.top ?? 0) + (content?.clientTop ?? 0);
  const visibleLeft = Math.max(chart.left, contentLeft, 0);
  const visibleRight = Math.min(chart.right, contentLeft + (content?.clientWidth ?? window.innerWidth), window.innerWidth);
  const visibleTop = Math.max(chart.top, contentTop, 0);
  const visibleBottom = Math.min(chart.bottom, contentTop + (content?.clientHeight ?? window.innerHeight), window.innerHeight);
  const availableHeight = Math.max(0, visibleBottom - visibleTop);

  const scrollTop = tip.scrollTop;
  tip.style.maxWidth = `${Math.max(0, visibleRight - visibleLeft)}px`;
  tip.style.maxHeight = `${availableHeight}px`;
  const measuredWidth = tip.getBoundingClientRect().width;
  const clearance = 12;
  const spacesAround = (anchorLeft: number, anchorRight: number) => [
    { left: Math.max(anchorRight, pointerX) + clearance, right: visibleRight },
    { left: visibleLeft, right: Math.min(anchorLeft, pointerX) - clearance, alignRight: true },
    { left: Math.min(anchorRight, pointerX) + clearance, right: Math.max(anchorLeft, pointerX) - clearance },
  ].map(space => {
    const left = Math.max(visibleLeft, space.left), right = Math.min(visibleRight, space.right);
    return { ...space, left, right, width: Math.max(0, right - left) };
  });
  let spaces = spacesAround(Math.min(guideX, barBounds?.left ?? guideX), Math.max(guideX, barBounds?.right ?? guideX));
  let space = spaces.find(candidate => candidate.width >= measuredWidth);
  if (!space && allowBarOverlap && barBounds) {
    spaces = spacesAround(guideX, guideX);
    space = spaces.find(candidate => candidate.width >= measuredWidth);
  }
  space ??= spaces.reduce((widest, candidate) => candidate.width > widest.width ? candidate : widest);

  tip.style.maxWidth = `${space.width}px`;
  const { width, height } = tip.getBoundingClientRect();
  // A sliver of the chart can be too small even for the tooltip's padding and border.
  const fits = width <= space.width && height <= availableHeight;
  tip.style.visibility = fits ? '' : 'hidden';
  if (fits) {
    const left = space.alignRight ? space.right - width : space.left;
    const top = Math.max(visibleTop, Math.min(chart.top + topOffset, visibleBottom - height));
    tip.style.left = `${left - chart.left - host.clientLeft}px`;
    tip.style.top = `${top - chart.top - host.clientTop}px`;
    tip.scrollTop = scrollTop;
  }
  const scrollable = fits && tip.scrollHeight > tip.clientHeight;
  tip.style.pointerEvents = scrollable ? 'auto' : 'none';
  return scrollable;
}
