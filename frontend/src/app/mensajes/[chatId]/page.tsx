import { ChatThreadView } from "@/components/marketplace/chat-thread-view";
import { MarketplaceFooter, MarketplaceHeader } from "@/components/marketplace/site-navigation";

export default async function ChatPage({ params }: { params: Promise<{ chatId: string }> }) {
  const { chatId } = await params;
  return (
    <>
      <MarketplaceHeader />
      <main className="marketplace-main chat-page" id="contenido">
        <ChatThreadView chatId={chatId} />
      </main>
      <MarketplaceFooter />
    </>
  );
}
