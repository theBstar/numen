import { useState, useCallback } from "react";

interface UseRovingFocusOptions {
  columnCount: number;
  getCardCount: (columnIndex: number) => number;
}

interface UseRovingFocusReturn {
  focusedColumn: number;
  focusedCard: number;
  setFocusedColumn: (col: number) => void;
  setFocusedCard: (card: number) => void;
  moveLeft: () => void;
  moveRight: () => void;
  moveUp: () => void;
  moveDown: () => void;
  reset: () => void;
  isActive: boolean;
  activate: () => void;
  deactivate: () => void;
}

export function useRovingFocus({ columnCount, getCardCount }: UseRovingFocusOptions): UseRovingFocusReturn {
  const [focusedColumn, setFocusedColumn] = useState(0);
  const [focusedCard, setFocusedCard] = useState(0);
  const [isActive, setIsActive] = useState(false);

  const activate = useCallback(() => setIsActive(true), []);
  const deactivate = useCallback(() => setIsActive(false), []);

  const moveLeft = useCallback(() => {
    setFocusedColumn((prev) => {
      const next = Math.max(0, prev - 1);
      const cardCount = getCardCount(next);
      setFocusedCard((prevCard) => Math.min(prevCard, Math.max(0, cardCount - 1)));
      return next;
    });
    setIsActive(true);
  }, [getCardCount]);

  const moveRight = useCallback(() => {
    setFocusedColumn((prev) => {
      const next = Math.min(columnCount - 1, prev + 1);
      const cardCount = getCardCount(next);
      setFocusedCard((prevCard) => Math.min(prevCard, Math.max(0, cardCount - 1)));
      return next;
    });
    setIsActive(true);
  }, [columnCount, getCardCount]);

  const moveUp = useCallback(() => {
    setFocusedCard((prev) => Math.max(0, prev - 1));
    setIsActive(true);
  }, []);

  const moveDown = useCallback(() => {
    setFocusedCard((prev) => {
      const cardCount = getCardCount(focusedColumn);
      return Math.min(cardCount - 1, prev + 1);
    });
    setIsActive(true);
  }, [focusedColumn, getCardCount]);

  const reset = useCallback(() => {
    setFocusedColumn(0);
    setFocusedCard(0);
    setIsActive(false);
  }, []);

  return {
    focusedColumn,
    focusedCard,
    setFocusedColumn,
    setFocusedCard,
    moveLeft,
    moveRight,
    moveUp,
    moveDown,
    reset,
    isActive,
    activate,
    deactivate,
  };
}
