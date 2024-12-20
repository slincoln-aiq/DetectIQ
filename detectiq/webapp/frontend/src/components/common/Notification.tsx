import { Snackbar, Alert } from '@mui/material';

interface NotificationProps {
  open: boolean;
  message: string;
  type: 'success' | 'error';
  onClose: () => void;
}

export default function Notification({ open, message, type, onClose }: NotificationProps) {
  return (
    <Snackbar
      open={open}
      autoHideDuration={6000}
      onClose={onClose}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      sx={{ 
        bottom: { xs: 16, sm: 24 },
        zIndex: 9999
      }}
    >
      <Alert 
        onClose={onClose}
        severity={type}
        variant="filled"
        elevation={6}
        sx={{ 
          width: '100%',
          minWidth: '300px',
          maxWidth: '600px',
          boxShadow: (theme) => theme.shadows[8],
          '& .MuiAlert-message': {
            fontSize: '0.95rem'
          }
        }}
      >
        {message}
      </Alert>
    </Snackbar>
  );
} 