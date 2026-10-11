import { ChatListView } from "@/components/marketplace/chat-list-view";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";

export default function MessagesPage() {
  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main chat-page" id="contenido">
        <a className="skip-link" href="#chat-list-title">Ir a los mensajes</a>
        <ChatListView />
      </main>
      <MarketplaceFooter />
    </>
  );
}
