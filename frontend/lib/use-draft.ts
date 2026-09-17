"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { api, put, errorText } from "./api";
import type { Draft } from "./types";
import { useApp } from "./context";

// The server owns revisions. The browser buffer only recovers this tab's
// unsaved work; it must never silently rebase over another saved revision.
export function useDraft(id: string) {
  const [draft, setDraft] = useState<Draft | null>(null),
    [saveState, setSaveState] = useState("loading"),
    [error, setError] = useState(""),
    [recovered, setRecovered] = useState(false);
  const current = useRef<Draft | null>(null),
    revision = useRef(0),
    dirty = useRef(false),
    inFlight = useRef(false),
    timer = useRef<ReturnType<typeof setTimeout> | null>(null),
    saving = useRef<Promise<Draft | null> | null>(null),
    mounted = useRef(true);
  const { guard } = useApp();
  const bufferKey = "connact-draft-buffer:" + id;
  const buffer = useCallback(() => {
    try {
      if ((dirty.current || inFlight.current) && current.current)
        sessionStorage.setItem(
          bufferKey,
          JSON.stringify({ ...current.current, revision: revision.current }),
        );
      else sessionStorage.removeItem(bufferKey);
    } catch {
      // Storage may be unavailable; the in-memory buffer and unload guard remain.
    }
  }, [bufferKey]);
  const accept = useCallback(
    (d: Draft) => {
      if (d.id !== id) return;
      if (timer.current) clearTimeout(timer.current);
      current.current = d;
      revision.current = d.revision;
      dirty.current = false;
      buffer();
      if (mounted.current) {
        setDraft(d);
        setSaveState("saved");
        setError("");
        setRecovered(false);
      }
    },
    [id, buffer],
  );
  const flush = useCallback(async (): Promise<Draft | null> => {
    if (timer.current) clearTimeout(timer.current);
    if (saving.current) return saving.current;
    if (!current.current || !dirty.current) return current.current;
    const run = async () => {
      try {
        while (dirty.current && current.current) {
          const snapshot = current.current;
          dirty.current = false;
          inFlight.current = true;
          if (mounted.current) setSaveState("saving");
          const saved = await put<Draft>("/drafts/" + id, {
            ...snapshot,
            revision: revision.current,
          });
          inFlight.current = false;
          revision.current = saved.revision;
          // A user may have typed while this request was in flight. Preserve
          // that buffer, then save it in the next iteration with the new revision.
          current.current = dirty.current
            ? {
                ...current.current,
                revision: saved.revision,
                updated_at: saved.updated_at,
                persona_version: saved.persona_version,
              }
            : saved;
          buffer();
          if (mounted.current) setDraft(current.current);
        }
        if (mounted.current) {
          setSaveState("saved");
          setError("");
          setRecovered(false);
        }
        return current.current;
      } catch (e) {
        inFlight.current = false;
        dirty.current = true;
        buffer();
        if (mounted.current) {
          setSaveState("error");
          setError(errorText(e));
        }
        throw e;
      } finally {
        saving.current = null;
      }
    };
    saving.current = run();
    return saving.current;
  }, [id, buffer]);
  const edit = useCallback(
    (patch: Partial<Draft>) => {
      if (!current.current) return;
      current.current = { ...current.current, ...patch, status: "draft" };
      setDraft(current.current);
      dirty.current = true;
      setSaveState("unsaved");
      buffer();
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => void flush().catch(() => {}), 650);
    },
    [flush, buffer],
  );
  const loadLatest = useCallback(async () => {
    if (timer.current) clearTimeout(timer.current);
    // Let an already submitted write settle before fetching the replacement.
    if (saving.current) await saving.current.catch(() => {});
    accept(await api<Draft>("/drafts/" + id));
  }, [id, accept]);
  useEffect(() => {
    mounted.current = true;
    let active = true;
    api<Draft>("/drafts/" + id)
      .then((d) => {
        if (!active) return;
        let cached: Draft | null = null;
        try {
          const raw = sessionStorage.getItem(bufferKey);
          if (raw) cached = JSON.parse(raw) as Draft;
        } catch {
          /* Ignore an unusable local recovery record. */
        }
        accept(d);
        if (cached?.id === id && typeof cached.revision === "number") {
          current.current = { ...d, ...cached };
          revision.current = cached.revision;
          dirty.current = true;
          setDraft(current.current);
          setRecovered(true);
          buffer();
          if (cached.revision !== d.revision) {
            setSaveState("error");
            setError(
              "A newer draft was saved elsewhere. Your unsaved text is recovered here. Copy your edits before loading the latest version.",
            );
          } else setSaveState("unsaved");
        }
      })
      .catch((e) => {
        if (active) {
          setError(errorText(e));
          setSaveState("error");
        }
      });
    return () => {
      active = false;
      mounted.current = false;
      if (timer.current) clearTimeout(timer.current);
      if (dirty.current) void flush().catch(() => {});
    };
  }, [id, accept, flush, buffer, bufferKey]);
  useEffect(() => {
    guard.current = flush;
    const prevent = (e: BeforeUnloadEvent) => {
      if (dirty.current || saving.current) {
        buffer();
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", prevent);
    return () => {
      if (guard.current === flush) guard.current = null;
      window.removeEventListener("beforeunload", prevent);
    };
  }, [guard, flush, buffer]);
  return {
    draft,
    saveState,
    error,
    recovered,
    edit,
    flush,
    accept,
    loadLatest,
    setError,
  };
}
