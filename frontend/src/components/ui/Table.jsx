export default function Table({ columns, data, renderRow, emptyMessage = 'No data' }) {
  return (
    <div className="overflow-x-auto rounded-xl bg-slate-900 border border-slate-700/50">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-700/50 bg-slate-800/50">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`px-4 py-3 font-medium text-slate-400 ${col.align === 'center' ? 'text-center' : ''} ${col.className || ''}`}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-700/50">
          {data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-sm text-slate-500">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map(renderRow)
          )}
        </tbody>
      </table>
    </div>
  );
}
