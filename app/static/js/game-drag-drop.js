/**
 * Game Drag-and-Drop Functionality
 *
 * Uses SortableJS to enable drag-and-drop editing of games in:
 * - Day View: drag between fields and time slots
 * - Week View: drag between days
 *
 * Also provides a cancel drop zone for cancelling games.
 */

(function() {
    'use strict';

    // State
    let isDragging = false;
    let pendingMove = null;
    let csrfToken = null;

    // Initialize on DOM ready
    document.addEventListener('DOMContentLoaded', function() {
        // Get CSRF token
        const csrfInput = document.querySelector('input[name="csrf_token"]');
        if (csrfInput) {
            csrfToken = csrfInput.value;
        }

        // Initialize based on page type
        if (document.querySelector('.day-grid')) {
            initDayViewDragDrop();
        }
        if (document.querySelector('.calendar-grid')) {
            initWeekViewDragDrop();
        }

        // Initialize modals
        initMoveModal();
        initCancelModal();
    });

    /**
     * Initialize drag-and-drop for Day View
     */
    function initDayViewDragDrop() {
        const fieldCells = document.querySelectorAll('.field-cell');
        const cancelZone = document.getElementById('cancel-zone');

        fieldCells.forEach(function(cell) {
            // Check if this cell has an allocation
            const hasAllocation = cell.dataset.allocated === 'true';

            new Sortable(cell, {
                group: {
                    name: 'day-games',
                    // Only allow drops into cells with allocations
                    put: hasAllocation
                },
                animation: 150,
                ghostClass: 'game-slot-ghost',
                chosenClass: 'game-slot-chosen',
                dragClass: 'game-slot-dragging',
                // Prevent dragging items out of non-allocated cells (shouldn't have any, but just in case)
                sort: hasAllocation,
                onStart: function(evt) {
                    isDragging = true;
                    document.body.classList.add('is-dragging');
                    if (cancelZone) {
                        cancelZone.classList.add('drag-active');
                    }
                    // Add visual indicator for non-allocated cells
                    document.querySelectorAll('.field-cell.slot-no-allocation').forEach(function(noAllocCell) {
                        noAllocCell.classList.add('drag-no-drop');
                    });
                },
                onEnd: function(evt) {
                    isDragging = false;
                    document.body.classList.remove('is-dragging');
                    if (cancelZone) {
                        cancelZone.classList.remove('drag-active');
                        cancelZone.classList.remove('drag-over');
                    }
                    // Remove visual indicator
                    document.querySelectorAll('.field-cell.drag-no-drop').forEach(function(noAllocCell) {
                        noAllocCell.classList.remove('drag-no-drop');
                    });

                    // Check if dropped in same location
                    if (evt.from === evt.to && evt.oldIndex === evt.newIndex) {
                        return;
                    }

                    // Double-check: don't allow drop into non-allocated cell
                    if (evt.to.dataset.allocated !== 'true') {
                        // Revert the move
                        evt.from.appendChild(evt.item);
                        showNotification('Cannot move game to a slot without allocation', 'error');
                        return;
                    }

                    const gameId = evt.item.dataset.gameId;
                    const newField = evt.to.dataset.field;
                    const newTime = evt.to.dataset.time;
                    const oldField = evt.from.dataset.field;
                    const oldTime = evt.from.dataset.time;

                    // Show confirmation modal
                    showMoveConfirmation({
                        gameId: gameId,
                        newField: newField,
                        newTime: newTime,
                        oldField: oldField,
                        oldTime: oldTime,
                        element: evt.item,
                        fromContainer: evt.from,
                        toContainer: evt.to
                    });
                }
            });
        });

        // Set up cancel zone
        if (cancelZone) {
            cancelZone.addEventListener('dragover', function(e) {
                if (isDragging) {
                    e.preventDefault();
                    cancelZone.classList.add('drag-over');
                }
            });

            cancelZone.addEventListener('dragleave', function(e) {
                cancelZone.classList.remove('drag-over');
            });

            cancelZone.addEventListener('drop', function(e) {
                e.preventDefault();
                cancelZone.classList.remove('drag-over');

                // Get the dragged element's game ID
                const draggedElement = document.querySelector('.game-slot-dragging, .game-slot-chosen');
                if (draggedElement) {
                    const gameId = draggedElement.dataset.gameId;
                    showCancelConfirmation(gameId, draggedElement);
                }
            });
        }
    }

    /**
     * Initialize drag-and-drop for Week View
     */
    function initWeekViewDragDrop() {
        const dayCells = document.querySelectorAll('.calendar-day .games-container');
        const cancelZone = document.getElementById('cancel-zone');

        dayCells.forEach(function(cell) {
            new Sortable(cell, {
                group: 'week-games',
                animation: 150,
                ghostClass: 'game-card-ghost',
                chosenClass: 'game-card-chosen',
                dragClass: 'game-card-dragging',
                onStart: function(evt) {
                    isDragging = true;
                    document.body.classList.add('is-dragging');
                    if (cancelZone) {
                        cancelZone.classList.add('drag-active');
                    }
                },
                onEnd: function(evt) {
                    isDragging = false;
                    document.body.classList.remove('is-dragging');
                    if (cancelZone) {
                        cancelZone.classList.remove('drag-active');
                        cancelZone.classList.remove('drag-over');
                    }

                    // Check if dropped in same day
                    const fromDay = evt.from.closest('.calendar-day');
                    const toDay = evt.to.closest('.calendar-day');
                    if (fromDay === toDay) {
                        return;
                    }

                    const gameId = evt.item.dataset.gameId;
                    const newDate = toDay.dataset.date;
                    const oldDate = fromDay.dataset.date;

                    // Show confirmation modal
                    showMoveConfirmation({
                        gameId: gameId,
                        newDate: newDate,
                        oldDate: oldDate,
                        element: evt.item,
                        fromContainer: evt.from,
                        toContainer: evt.to
                    });
                }
            });
        });

        // Set up cancel zone (same as day view)
        if (cancelZone) {
            cancelZone.addEventListener('dragover', function(e) {
                if (isDragging) {
                    e.preventDefault();
                    cancelZone.classList.add('drag-over');
                }
            });

            cancelZone.addEventListener('dragleave', function(e) {
                cancelZone.classList.remove('drag-over');
            });

            cancelZone.addEventListener('drop', function(e) {
                e.preventDefault();
                cancelZone.classList.remove('drag-over');

                const draggedElement = document.querySelector('.game-card-dragging, .game-card-chosen');
                if (draggedElement) {
                    const gameId = draggedElement.dataset.gameId;
                    showCancelConfirmation(gameId, draggedElement);
                }
            });
        }
    }

    /**
     * Initialize move confirmation modal
     */
    function initMoveModal() {
        const modal = document.getElementById('move-confirm-modal');
        if (!modal) return;

        // Close on backdrop click
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeMoveModal(true); // revert
            }
        });

        // Close on Escape
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && modal.style.display === 'flex') {
                closeMoveModal(true); // revert
            }
        });

        // Confirm button
        const confirmBtn = document.getElementById('move-confirm-btn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', function() {
                confirmMove();
            });
        }

        // Cancel button
        const cancelBtn = document.getElementById('move-cancel-btn');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', function() {
                closeMoveModal(true); // revert
            });
        }
    }

    /**
     * Initialize cancel confirmation modal
     */
    function initCancelModal() {
        const modal = document.getElementById('cancel-confirm-modal');
        if (!modal) return;

        // Close on backdrop click
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeCancelModal();
            }
        });

        // Close on Escape
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && modal.style.display === 'flex') {
                closeCancelModal();
            }
        });

        // Confirm button
        const confirmBtn = document.getElementById('cancel-confirm-btn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', function() {
                confirmCancel();
            });
        }

        // Cancel button
        const cancelBtn = document.getElementById('cancel-cancel-btn');
        if (cancelBtn) {
            cancelBtn.addEventListener('click', function() {
                closeCancelModal();
            });
        }
    }

    /**
     * Show move confirmation modal
     */
    function showMoveConfirmation(moveData) {
        pendingMove = moveData;

        const modal = document.getElementById('move-confirm-modal');
        if (!modal) {
            // No modal, just confirm directly
            confirmMove();
            return;
        }

        // Update modal content
        const details = document.getElementById('move-details');
        if (details) {
            let text = '';
            if (moveData.newField && moveData.oldField !== moveData.newField) {
                text += `Field: ${moveData.oldField || 'TBD'} → ${moveData.newField}\n`;
            }
            if (moveData.newTime && moveData.oldTime !== moveData.newTime) {
                text += `Time: ${formatTime(moveData.oldTime)} → ${formatTime(moveData.newTime)}\n`;
            }
            if (moveData.newDate && moveData.oldDate !== moveData.newDate) {
                text += `Date: ${formatDate(moveData.oldDate)} → ${formatDate(moveData.newDate)}\n`;
            }
            details.textContent = text || 'Move game to new location';
        }

        // Clear reason field
        const reasonField = document.getElementById('move-reason');
        if (reasonField) {
            reasonField.value = '';
        }

        modal.style.display = 'flex';
    }

    /**
     * Close move confirmation modal
     */
    function closeMoveModal(revert) {
        const modal = document.getElementById('move-confirm-modal');
        if (modal) {
            modal.style.display = 'none';
        }

        // Revert the drag if needed
        if (revert && pendingMove) {
            pendingMove.fromContainer.appendChild(pendingMove.element);
        }

        pendingMove = null;
    }

    /**
     * Confirm and execute the move
     */
    function confirmMove() {
        if (!pendingMove) return;

        const reasonField = document.getElementById('move-reason');
        const reason = reasonField ? reasonField.value : '';

        // Check if this is a proposed game
        const isProposed = pendingMove.element.dataset.isProposed === 'true';

        // Get season context
        const yearEl = document.getElementById('season-year');
        const isSpringEl = document.getElementById('season-is-spring');
        const year = yearEl ? yearEl.value : null;
        const isSpring = isSpringEl ? isSpringEl.value : null;

        // Build request data
        const data = {
            game_id: pendingMove.gameId,
            reason: reason
        };

        // Add proposal context if this is a proposed game
        if (isProposed && year !== null && isSpring !== null) {
            data.is_proposed = true;
            data.year = parseInt(year, 10);
            data.is_spring = parseInt(isSpring, 10);
        }

        if (pendingMove.newField) {
            data.new_field = pendingMove.newField;
        }
        if (pendingMove.newTime) {
            data.new_time = pendingMove.newTime;
        }
        if (pendingMove.newDate) {
            data.new_date = pendingMove.newDate;
        }

        // Send API request
        fetch('/games/api/move-game', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(data)
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(result) {
            if (result.success) {
                // Update UI to reflect new state
                updateGameElement(pendingMove.element, pendingMove);
                showNotification('Game moved successfully', 'success');
                if (result.notifications_queued > 0) {
                    showNotification(`${result.notifications_queued} notifications queued`, 'info');
                }
            } else {
                // Revert on failure
                pendingMove.fromContainer.appendChild(pendingMove.element);
                showNotification(result.message || 'Failed to move game', 'error');
            }
            closeMoveModal(false);
        })
        .catch(function(error) {
            console.error('Error moving game:', error);
            pendingMove.fromContainer.appendChild(pendingMove.element);
            showNotification('Error moving game', 'error');
            closeMoveModal(false);
        });
    }

    /**
     * Show cancel confirmation modal
     */
    let pendingCancel = null;

    function showCancelConfirmation(gameId, element) {
        pendingCancel = { gameId: gameId, element: element };

        const modal = document.getElementById('cancel-confirm-modal');
        if (!modal) {
            confirmCancel();
            return;
        }

        // Clear reason field
        const reasonField = document.getElementById('cancel-reason');
        if (reasonField) {
            reasonField.value = '';
        }

        modal.style.display = 'flex';
    }

    /**
     * Close cancel confirmation modal
     */
    function closeCancelModal() {
        const modal = document.getElementById('cancel-confirm-modal');
        if (modal) {
            modal.style.display = 'none';
        }
        pendingCancel = null;
    }

    /**
     * Confirm and execute the cancellation
     */
    function confirmCancel() {
        if (!pendingCancel) return;

        const reasonField = document.getElementById('cancel-reason');
        const reason = reasonField ? reasonField.value : '';

        fetch('/games/api/cancel-game', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({
                game_id: pendingCancel.gameId,
                reason: reason
            })
        })
        .then(function(response) {
            return response.json();
        })
        .then(function(result) {
            if (result.success) {
                // Mark game as cancelled in UI
                markGameCancelled(pendingCancel.element);
                showNotification('Game cancelled', 'success');
                if (result.notifications_queued > 0) {
                    showNotification(`${result.notifications_queued} notifications queued`, 'info');
                }
            } else {
                showNotification(result.message || 'Failed to cancel game', 'error');
            }
            closeCancelModal();
        })
        .catch(function(error) {
            console.error('Error cancelling game:', error);
            showNotification('Error cancelling game', 'error');
            closeCancelModal();
        });
    }

    /**
     * Update game element after move
     */
    function updateGameElement(element, moveData) {
        // Update time display if changed
        if (moveData.newTime) {
            const timeEl = element.querySelector('.game-time');
            if (timeEl) {
                const timeText = timeEl.textContent;
                // Keep status dot, update time
                const statusDot = timeEl.querySelector('.status-dot');
                if (statusDot) {
                    timeEl.innerHTML = '';
                    timeEl.appendChild(statusDot);
                    timeEl.appendChild(document.createTextNode(' ' + formatTime(moveData.newTime)));
                }
            }
        }
    }

    /**
     * Mark game as cancelled in UI
     */
    function markGameCancelled(element) {
        element.classList.add('cancelled');
        element.style.opacity = '0.4';
        element.style.textDecoration = 'line-through';

        // Update status dot
        const statusDot = element.querySelector('.status-dot');
        if (statusDot) {
            statusDot.className = 'status-dot cancelled';
        }
    }

    /**
     * Show a notification message
     */
    function showNotification(message, type) {
        // Create notification element
        const notif = document.createElement('div');
        notif.className = 'drag-drop-notification ' + type;
        notif.textContent = message;
        notif.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            border-radius: 4px;
            color: white;
            font-weight: 500;
            z-index: 9999;
            animation: slideIn 0.3s ease;
        `;

        if (type === 'success') {
            notif.style.backgroundColor = 'rgb(34, 139, 34)';
        } else if (type === 'error') {
            notif.style.backgroundColor = '#c33';
        } else {
            notif.style.backgroundColor = 'rgb(255, 140, 0)';
        }

        document.body.appendChild(notif);

        // Remove after 3 seconds
        setTimeout(function() {
            notif.style.animation = 'slideOut 0.3s ease';
            setTimeout(function() {
                notif.remove();
            }, 300);
        }, 3000);
    }

    /**
     * Format time for display (HH:MM -> h:MM AM/PM)
     */
    function formatTime(timeStr) {
        if (!timeStr) return 'TBD';
        const parts = timeStr.split(':');
        let hour = parseInt(parts[0], 10);
        const minute = parts[1];
        const ampm = hour >= 12 ? 'PM' : 'AM';
        hour = hour % 12 || 12;
        return hour + ':' + minute + ' ' + ampm;
    }

    /**
     * Format date for display (YYYY-MM-DD -> Month DD)
     */
    function formatDate(dateStr) {
        if (!dateStr) return 'TBD';
        const date = new Date(dateStr + 'T00:00:00');
        const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        return months[date.getMonth()] + ' ' + date.getDate();
    }

    // Add CSS for animations
    const style = document.createElement('style');
    style.textContent = `
        @keyframes slideIn {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
        }
        @keyframes slideOut {
            from { transform: translateX(0); opacity: 1; }
            to { transform: translateX(100%); opacity: 0; }
        }
        .game-slot-ghost, .game-card-ghost {
            opacity: 0.4;
            background: #c8e6c9 !important;
        }
        .game-slot-chosen, .game-card-chosen {
            transform: scale(1.02);
            box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
        }
        .game-slot-dragging, .game-card-dragging {
            opacity: 0.8;
        }
        .cancel-drop-zone {
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            padding: 20px 40px;
            background: #ffebee;
            border: 2px dashed #c62828;
            border-radius: 8px;
            display: none;
            font-weight: 500;
            color: #c62828;
            z-index: 1000;
        }
        .cancel-drop-zone.drag-active {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .cancel-drop-zone.drag-over {
            background: #ffcdd2;
            border-style: solid;
            transform: translateX(-50%) scale(1.05);
        }
        body.is-dragging .cancel-drop-zone {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        /* Visual indicator for non-allocated cells during drag */
        .field-cell.drag-no-drop {
            background: #ffebee !important;
            position: relative;
        }
        .field-cell.drag-no-drop::after {
            content: 'X';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 24px;
            color: #c62828;
            opacity: 0.3;
            pointer-events: none;
        }
    `;
    document.head.appendChild(style);

})();
