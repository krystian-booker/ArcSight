/**
 * Select dropdown component with label and error support
 */

import { forwardRef } from 'react';
import type { SelectHTMLAttributes } from 'react';

interface SelectOption {
  value: string | number;
  label: string;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  helperText?: string;
  options: SelectOption[];
  placeholder?: string;
}

const Select = forwardRef<HTMLSelectElement, SelectProps>(
  ({ label, error, helperText, options, placeholder, className = '', ...props }, ref) => {
    const selectId = props.id || `select-${Math.random().toString(36).substr(2, 9)}`;

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={selectId}
            className="mb-2xs block text-[0.85rem] font-medium uppercase tracking-arc-tight text-arc-accent"
          >
            {label}
            {props.required && <span className="ml-1 text-arc-danger">*</span>}
          </label>
        )}
        <select
          ref={ref}
          id={selectId}
          className={`
            w-full rounded-arc-sm form-control-bg px-[0.9rem] py-[0.7rem] pr-10
            text-arc-text appearance-none
            transition-all duration-arc ease-arc-out
            focus:outline-none focus:border-arc-teal/60 focus:shadow-[0_0_0_2px_rgba(0,194,168,0.25)]
            disabled:cursor-not-allowed disabled:opacity-50
            ${error ? 'border-arc-danger' : 'hover:border-white/8'}
            ${className}
          `}
          style={{
            backgroundImage: `linear-gradient(45deg, transparent 50%, rgba(191, 196, 202, 0.6) 50%), linear-gradient(135deg, rgba(191, 196, 202, 0.6) 50%, transparent 50%)`,
            backgroundPosition: 'calc(100% - 20px) calc(50% - 3px), calc(100% - 14px) calc(50% - 3px)',
            backgroundSize: '6px 6px, 6px 6px',
            backgroundRepeat: 'no-repeat',
          }}
          {...props}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        {error && <p className="mt-2xs text-sm text-arc-danger">{error}</p>}
        {helperText && !error && (
          <p className="mt-2xs text-sm text-arc-subtle">{helperText}</p>
        )}
      </div>
    );
  }
);

Select.displayName = 'Select';

export default Select;
