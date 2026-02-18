const VARIANTS = {
  default: '',
  interactive: 'hover:-translate-y-0.5 hover:border-slate-600 hover:shadow-lg hover:shadow-slate-950/50 transition-all cursor-pointer',
  elevated: 'shadow-lg shadow-slate-950/50',
};

export default function Card({ variant = 'default', className = '', children, ...rest }) {
  return (
    <div className={`rounded-xl bg-slate-900 border border-slate-700/50 ${VARIANTS[variant]} ${className}`} {...rest}>
      {children}
    </div>
  );
}

Card.Header = function CardHeader({ className = '', children }) {
  return <div className={`border-b border-slate-700/50 px-5 py-4 ${className}`}>{children}</div>;
};

Card.Body = function CardBody({ className = '', children }) {
  return <div className={`px-5 py-4 ${className}`}>{children}</div>;
};

Card.Footer = function CardFooter({ className = '', children }) {
  return <div className={`border-t border-slate-700/50 px-5 py-4 ${className}`}>{children}</div>;
};
