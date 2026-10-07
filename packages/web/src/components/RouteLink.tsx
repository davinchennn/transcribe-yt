import type { AnchorHTMLAttributes, MouseEvent } from 'react';
import { navigate } from '../lib/routing';

type RouteLinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> & { href: string };

export function RouteLink({ href, onClick, ...props }: RouteLinkProps) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    onClick?.(event);
    const link = event.currentTarget;
    if (
      event.defaultPrevented || event.button !== 0 ||
      event.metaKey || event.ctrlKey || event.shiftKey || event.altKey ||
      (link.target && link.target.toLowerCase() !== '_self') ||
      link.hasAttribute('download') || link.rel.toLowerCase().split(/\s+/).includes('external')
    ) return;

    let url: URL;
    try {
      url = new URL(link.href, window.location.href);
    } catch {
      return;
    }
    if (url.origin !== window.location.origin || url.protocol !== window.location.protocol) return;
    event.preventDefault();
    navigate(url.href);
  }

  return <a {...props} href={href} onClick={handleClick} />;
}
