import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// Standard shadcn/ui helper: merge conditional classnames (clsx) then
// resolve conflicting Tailwind utilities in favor of the last one (twMerge).
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
