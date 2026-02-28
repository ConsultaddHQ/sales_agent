import { useConversation } from "@elevenlabs/react";
import { useState, useEffect, useRef } from "react";
import { Mic, Pause, Play, X, Send } from "lucide-react";
import { motion } from "framer-motion";

type Product = {
  id: string;
  name: string;
  price: number;
  image_url: string;
  description: string;
};

function Widget() {
  const storeId = window.__HYPERFLEX_WIDGET_STORE_ID__ || "aa538422-17d1-4b2c-8d02-d512405d929b";
  const position: "bottom-left" | "bottom-right" = window.__HYPERFLEX_WIDGET_POSITION__ || "bottom-right";
  const agentId = window.__HYPERFLEX_WIDGET_AGENT_ID__ || "";

  const [transcription, setTranscription] = useState("");
  const [isPaused, setIsPaused] = useState(false);
  const [products, setProducts] = useState<Product[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [textInput, setTextInput] = useState(""); // For text fallback
  const isStarting = useRef(false); // Prevent double starts

  const conversation = useConversation({
    micMuted: isPaused,
    clientTools: {
      update_products: (params: { products: Product[] }) => {
        setProducts(params.products || []);
      },
      highlight_product: (params: { product_id: string }) => {
        const el = document.getElementById(`product-${params.product_id}`);
        if (el) el.classList.add("ring-4", "ring-green-400");
        setTimeout(() => el?.classList.remove("ring-4", "ring-green-400"), 4000);
      },
      focus_product: (params: { product_id: string }) => {
        document.getElementById(`product-${params.product_id}`)?.scrollIntoView({ behavior: "smooth" });
      },
    },
    onMessage: (msg) => {
      if (msg.source === "user" || msg.source === "ai") setTranscription(msg.message ?? "");
    },
    onError: (message) => setError(message),
  });

  const { status, sendUserMessage } = conversation;

  // Start session with voice mode
  useEffect(() => {
    if (isOpen && status === "disconnected" && agentId && !isStarting.current) {
      isStarting.current = true;
      const start = async () => {
        if (!agentId) {
          setError("Missing agent ID");
          isStarting.current = false;
          return;
        }
        try {
          // Pre-request microphone permission to avoid repeated prompts
          await navigator.mediaDevices.getUserMedia({ audio: true });
          await conversation.startSession({
            agentId,
            connectionType: "webrtc", // Use WebRTC for low-latency voice mode
            dynamicVariables: { store_id: storeId },
          });
          setError(null);
        } catch (err: unknown) {
          setError((err as Error).message || "Connection failed. Check microphone permissions and agent configuration.");
        } finally {
          isStarting.current = false;
        }
      };
      start();
    }
  }, [isOpen, status, agentId, storeId, conversation]);

  // Cleanup session on close/unmount
  useEffect(() => {
    return () => {
      if (status === "connected" || status === "connecting") {
        conversation.endSession().catch(console.error);
      }
    };
  }, [status, conversation]);

  // Send text input (fallback)
  const handleSendText = () => {
    if (textInput.trim()) {
      sendUserMessage(textInput);
      setTextInput("");
    }
  };

  const justify = position === "bottom-right" ? "justify-end" : "justify-start";

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className={`fixed bottom-6 ${position === "bottom-left" ? "left-6" : "right-6"} w-14 h-14 bg-gradient-to-r from-purple-600 to-pink-600 rounded-full shadow-lg flex items-center justify-center z-50 hover:scale-105 transition-all`}
      >
        <Mic className="w-6 h-6 text-white" />
      </button>

      {isOpen && (
        <div className={`fixed inset-0 bg-black/50 z-50 flex items-end ${justify} p-4`}>
          <motion.div
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ duration: 0.3 }}
            className="bg-white rounded-t-2xl w-full max-w-md h-[70vh] flex flex-col overflow-hidden shadow-xl"
          >
            {/* Header */}
            <div className="bg-gradient-to-r from-purple-600 to-pink-600 p-4 text-white flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Mic className="w-5 h-5" />
                <div>
                  <p className="font-semibold">Shop Assistant</p>
                  <p className="text-xs">{error || status}</p>
                </div>
              </div>
              <button onClick={() => setIsOpen(false)}><X className="w-5 h-5" /></button>
            </div>

            {/* Transcription */}
            <div className="p-4 bg-gray-100 text-sm flex-0 min-h-[60px]">
              {transcription || "Speak or type..."}
            </div>

            {/* Products */}
            <div className="flex-1 overflow-auto p-4 space-y-4">
              {products.length > 0 ? products.map((p) => (
                <div key={p.id} id={`product-${p.id}`} className="bg-white p-3 rounded-lg shadow flex gap-3">
                  <img src={p.image_url} alt={p.name} className="w-16 h-16 object-cover rounded" />
                  <div>
                    <p className="font-medium">{p.name}</p>
                    <p className="text-green-600">${p.price}</p>
                    <p className="text-xs text-gray-600">{p.description}</p>
                  </div>
                </div>
              )) : <p className="text-center text-gray-500">Ask about products!</p>}
            </div>

            {/* Controls + Text Fallback */}
            <div className="p-4 bg-white border-t flex gap-2">
              <input
                type="text"
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSendText()}
                placeholder="Type your query (or speak)..."
                className="flex-1 p-2 border rounded"
              />
              <button onClick={handleSendText} className="p-2 bg-purple-600 text-white rounded"><Send className="w-5 h-5" /></button>
              <button onClick={() => setIsPaused(!isPaused)} disabled={status !== "connected"} className="p-2 bg-gray-200 rounded">
                {isPaused ? <Play className="w-5 h-5" /> : <Pause className="w-5 h-5" />}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </>
  );
}

export default Widget;