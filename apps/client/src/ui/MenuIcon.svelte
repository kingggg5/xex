<script lang="ts">let { name }: { name: string } = $props();</script>
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
{#if name === "character"}<circle cx="12" cy="7" r="3.2"/><path d="M5 20v-3c0-6 14-6 14 0v3ZM9 3l3-2 3 2"/>
{:else if name === "bag"}<path d="M8 8V6c0-5 8-5 8 0v2M4 8h16v12H4ZM8 14h8M10 13v3"/>
{:else if name === "skills"}<path d="m12 2 3 6 7 4-7 3-3 7-3-7-7-3 7-4Z"/><path d="M12 8v8m-4-4h8"/>
{:else if name === "friends"}<path d="M3 4h7l2 2 2-2h7v16h-7l-2 2-2-2H3ZM12 6v16M6 9h3m6 0h3M6 13h3m6 0h3"/>
{:else if name === "group"}<circle cx="8" cy="7" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M2 20v-3c0-6 12-6 12 0v3ZM15 15c4-1 7 1 7 4v1"/>
{:else if name === "map"}<path d="m2 6 7-3 6 3 7-3v15l-7 3-6-3-7 3ZM9 3v15m6-12v15"/><path d="m18 8 1-1 1 1-1 3Z"/>
{:else if name === "store"}<path d="M3 10h18l-3-7H6ZM5 10v11h14V10M9 21v-7h6v7M3 10c0 4 6 4 6 0 0 4 6 4 6 0 0 4 6 4 6 0"/>
{:else if name === "tower"}<path d="M8 21V9l4-7 4 7v12M6 21h12M8 9h8m-5 4h2m-2 4h2"/>
{:else}<path d="m9 2-1 4-3 1-3-1-1 5 3 2 1 3-1 4 5 2 3-3 3 1 4 1 2-5-3-3V9l3-3-4-4-4 2Z"/><circle cx="12" cy="12" r="3"/>{/if}
</svg>
