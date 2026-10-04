export interface MobileWebAppView { language: 'th' | 'en'; portrait: boolean; standalone: boolean; guideOpen: boolean }
export interface MobileWebAppController { isBlocked(): boolean; onBlockedChange(callback: (blocked: boolean) => void): () => void; openGuide(): void; dispose(): void }
