import { Bot } from 'lucide-react';

export function Header() {
  return (
    <header className="border-b border-border bg-card">
      <div className="container mx-auto flex h-14 items-center gap-3 px-4">
        <Bot className="h-6 w-6 text-primary" />
        <h1 className="text-lg font-semibold">TweetGod Dashboard</h1>
      </div>
    </header>
  );
}
