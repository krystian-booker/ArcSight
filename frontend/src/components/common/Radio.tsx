/**
 * Radio button component with label support
 */

import { forwardRef } from 'react';
import type { InputHTMLAttributes } from 'react';

interface RadioProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: string;
  description?: string;
  error?: string;
}

const Radio = forwardRef<HTMLInputElement, RadioProps>(
  ({ label, description, error, className = '', ...props }, ref) => {
    const radioId = props.id || `radio-${Math.random().toString(36).substr(2, 9)}`;

    return (
      <div className="flex items-start">
        <div className="flex h-5 items-center">
          <input
            ref={ref}
            id={radioId}
            type="radio"
            className={`
              h-4 w-4 border-arc-border bg-arc-surface
              text-arc-primary
              focus:ring-2 focus:ring-arc-teal focus:ring-offset-2 focus:ring-offset-arc-bg
              disabled:cursor-not-allowed disabled:opacity-50
              transition-colors duration-arc-fast
              ${error ? 'border-arc-danger' : ''}
              ${className}
            `}
            {...props}
          />
        </div>
        {(label || description) && (
          <div className="ml-sm">
            {label && (
              <label
                htmlFor={radioId}
                className="block text-sm font-medium text-arc-text cursor-pointer"
              >
                {label}
              </label>
            )}
            {description && (
              <p className="text-sm text-arc-subtle">{description}</p>
            )}
            {error && <p className="mt-2xs text-sm text-arc-danger">{error}</p>}
          </div>
        )}
      </div>
    );
  }
);

Radio.displayName = 'Radio';

export default Radio;
