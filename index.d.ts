export type IconStyle = 'monochrome' | 'color';
export type IconArtwork = 'icon' | 'brand' | 'text' | 'text-cn';
export interface IconOptions { style?: IconStyle; variant?: string; artwork?: IconArtwork }
export interface IconArtworkFiles { monochrome: string; color?: string }
export interface ProviderIconEntry extends IconArtworkFiles { name: string; alternatives: string[]; artworks?: Partial<Record<Exclude<IconArtwork, 'icon'>, IconArtworkFiles>> }
export interface ResolvedIcon { id: string; name: string; file: string; style: IconStyle; requestedStyle: IconStyle; artwork: IconArtwork; alternatives: string[] }
export const providerIconVersion: string;
export const providerIcons: Readonly<Record<string, ProviderIconEntry>>;
export const providerAliases: Readonly<Record<string, string>>;
export const PROVIDER_ICON_FILES: Readonly<Record<string, string>>;
export function resolveProviderIcon(provider: string, options?: IconOptions): ResolvedIcon | undefined;
export const providerIconComponentNames: Readonly<Record<string, string>>;
