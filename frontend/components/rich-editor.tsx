"use client";
import { useEffect, useState } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import {
  Bold,
  Italic,
  List,
  ListOrdered,
  Link2,
  Undo2,
  Redo2,
  Unlink,
} from "lucide-react";
import { useApp } from "@/lib/context";
export default function RichEditor({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (s: string) => void;
  disabled: boolean;
}) {
  const { t } = useApp();
  const [showLink, setShowLink] = useState(false),
    [url, setUrl] = useState("");
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        link: false,
        heading: false,
        blockquote: false,
        codeBlock: false,
        code: false,
        horizontalRule: false,
        strike: false,
      }),
      Link.configure({
        openOnClick: false,
        protocols: ["http", "https", "mailto"],
        HTMLAttributes: { rel: "noopener noreferrer" },
      }),
    ],
    content: value,
    immediatelyRender: false,
    shouldRerenderOnTransaction: true,
    editorProps: {
      attributes: {
        class: "email-content",
        role: "textbox",
        "aria-label": "Email body",
        "aria-multiline": "true",
      },
    },
    onUpdate: ({ editor }) => onChange(editor.getHTML()),
  });
  useEffect(() => {
    if (editor && editor.getHTML() !== value)
      editor.commands.setContent(value, { emitUpdate: false });
  }, [editor, value]);
  useEffect(() => {
    editor?.setEditable(!disabled, false);
  }, [editor, disabled]);
  if (!editor)
    return (
      <div className="editor-loading">
        {t("Loading editor…", "加载编辑器…")}
      </div>
    );
  return (
    <div className="rich-editor">
      <div className="editor-toolbar" onMouseDown={(e) => e.preventDefault()}>
        <button
          aria-label="Bold"
          title={t("Bold", "加粗")}
          className={editor.isActive("bold") ? "selected" : ""}
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleBold().run()}
        >
          <Bold size={16} />
        </button>
        <button
          aria-label="Italic"
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleItalic().run()}
        >
          <Italic size={16} />
        </button>
        <span />
        <button
          aria-label="Bullet list"
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleBulletList().run()}
        >
          <List size={17} />
        </button>
        <button
          aria-label="Ordered list"
          disabled={disabled}
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
        >
          <ListOrdered size={17} />
        </button>
        <button
          aria-label="Add link"
          disabled={disabled}
          onClick={() => {
            setUrl(editor.getAttributes("link").href || "");
            setShowLink(!showLink);
          }}
        >
          <Link2 size={16} />
        </button>
        <button
          aria-label="Remove link"
          disabled={disabled}
          onClick={() => editor.chain().focus().unsetLink().run()}
        >
          <Unlink size={15} />
        </button>
        <span />
        <button
          aria-label="Undo"
          disabled={disabled}
          onClick={() => editor.chain().focus().undo().run()}
        >
          <Undo2 size={16} />
        </button>
        <button
          aria-label="Redo"
          disabled={disabled}
          onClick={() => editor.chain().focus().redo().run()}
        >
          <Redo2 size={16} />
        </button>
        <small>{t("Rich text", "富文本")}</small>
      </div>
      {showLink && (
        <form
          className="link-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (/^(https?:\/\/|mailto:)/.test(url)) {
              editor
                .chain()
                .focus()
                .extendMarkRange("link")
                .setLink({ href: url })
                .run();
              setShowLink(false);
            }
          }}
        >
          <input
            aria-label="Link URL"
            type="url"
            placeholder="https://example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
            pattern="https?://.*"
          />
          <button className="button small-button">
            {t("Apply link", "插入链接")}
          </button>
        </form>
      )}
      <EditorContent editor={editor} />
      <div className="editor-foot">
        <span>
          {editor.getText().split(/\s+/).filter(Boolean).length}{" "}
          {t("words", "词")}
        </span>
        <span>
          {t("Personal, specific, and to the point.", "个性化、具体、简明。")}
        </span>
      </div>
    </div>
  );
}
