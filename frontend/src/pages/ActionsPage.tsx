/**
 * ActionsPage - Dedicated page for action approval and management
 * Similar to AlertsPage pattern
 */

import { useState } from 'react';
import { ActionList } from '../components/actions/ActionList';

export function ActionsPage() {
  const [selectedProject, setSelectedProject] = useState<string>('');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--color-text)]">Actions</h1>
          <p className="text-[var(--color-text-secondary)]">
            Approve and manage AI-generated actions
          </p>
        </div>
      </div>

      {/* Project Filter */}
      <div className="flex items-center gap-4">
        <label className="text-sm text-[var(--color-text-secondary)]">Project:</label>
        <select
          value={selectedProject}
          onChange={(e) => setSelectedProject(e.target.value)}
          className="bg-white/5 border border-[var(--color-border)] rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-[var(--color-accent)]"
        >
          <option value="">All Projects</option>
          <option value="meinvoice">meinvoice</option>
          {/* Add more projects as needed */}
        </select>
      </div>

      {/* Actions List */}
      <ActionList project={selectedProject || undefined} />
    </div>
  );
}
