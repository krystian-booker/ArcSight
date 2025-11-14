import { useState, useEffect } from 'react'
import { Settings as SettingsIcon, Network, Tag, HardDrive, AlertTriangle } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { toast } from '@/hooks/use-toast'
import { api } from '@/lib/api'

type FieldOption = {
  value: string
  label: string
  isDefault: boolean
}

const formatFieldLabel = (name: string) =>
  name
    .replace(/\.json$/i, '')
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')

export default function Settings() {
  const [teamNumber, setTeamNumber] = useState('')
  const [hostname, setHostname] = useState('')
  const [ipMode, setIpMode] = useState<'dhcp' | 'static'>('dhcp')
  const [genicamPath, setGenicamPath] = useState('')
  const [selectedField, setSelectedField] = useState('')
  const [fieldOptions, setFieldOptions] = useState<FieldOption[]>([])
  const [confirmAction, setConfirmAction] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  // Load settings on component mount
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const data = await api.get<{
          settings: {
            team_number: string
            hostname: string
            ip_mode: 'dhcp' | 'static'
            genicam_cti_path: string
          }
          selected_field: string
          default_fields?: { name: string; is_default: boolean }[]
          user_fields?: { name: string; is_default: boolean }[]
        }>('/settings/api/settings')
        setTeamNumber(data.settings.team_number || '')
        setHostname(data.settings.hostname || '')
        setIpMode(data.settings.ip_mode || 'dhcp')
        setGenicamPath(data.settings.genicam_cti_path || '')
        setSelectedField(data.selected_field || '')

        const fields = [
          ...(data.default_fields ?? []),
          ...(data.user_fields ?? []),
        ].map<FieldOption>((field) => ({
          value: field.name,
          label: formatFieldLabel(field.name),
          isDefault: field.is_default,
        }))

        setFieldOptions(fields)
      } catch (error) {
        console.error('Failed to load settings:', error)
        toast({
          variant: 'destructive',
          title: 'Error',
          description: 'Failed to load settings',
        })
      }
    }
    loadSettings()
  }, [])

  const handleSaveGlobal = async () => {
    setIsLoading(true)
    try {
      await api.post('/settings/global/update', {
        team_number: teamNumber,
        hostname: hostname,
        ip_mode: ipMode,
      })
      toast({
        title: 'Settings saved',
        description: 'Global settings updated successfully',
      })
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to save settings',
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleSaveGenICam = async () => {
    setIsLoading(true)
    try {
      await api.post('/settings/genicam/update', {
        genicam_cti_path: genicamPath,
      })
      toast({
        title: 'GenICam configured',
        description: 'CTI path updated successfully',
      })
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to update GenICam settings',
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleClearGenICam = async () => {
    setIsLoading(true)
    try {
      await api.post('/settings/genicam/clear')
      setGenicamPath('')
      toast({
        title: 'GenICam cleared',
        description: 'CTI path removed',
      })
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to clear GenICam settings',
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleFieldChange = async (fieldName: string) => {
    const previous = selectedField
    setSelectedField(fieldName)
    try {
      await api.post('/settings/apriltag/select', {
        field_name: fieldName,
      })
      const label = fieldOptions.find((option) => option.value === fieldName)?.label || fieldName
      toast({
        title: 'Field layout updated',
        description: `Selected ${label}`,
      })
    } catch (error) {
      setSelectedField(previous)
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to save field selection',
      })
    }
  }

  const handleSystemAction = async (action: string) => {
    setConfirmAction(null)
    setIsLoading(true)

    try {
      switch (action) {
        case 'restart':
          await api.post('/settings/control/restart-app')
          toast({
            title: 'Restarting',
            description: 'Application is restarting...',
          })
          break
        case 'reboot':
          await api.post('/settings/control/reboot')
          toast({
            title: 'Rebooting',
            description: 'System is rebooting...',
          })
          break
        case 'factory-reset':
          await api.post('/settings/control/factory-reset')
          toast({
            title: 'Reset complete',
            description: 'All settings have been reset to defaults',
          })
          break
      }
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: `Failed to ${action}`,
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleExportDatabase = async () => {
    try {
      window.location.href = '/settings/control/export-db'
      toast({
        title: 'Export started',
        description: 'Downloading database file...',
      })
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Error',
        description: 'Failed to export database',
      })
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-semibold mb-2">Settings</h1>
        <p className="text-muted">Application and system configuration</p>
      </div>

      <Tabs defaultValue="global" className="space-y-4">
        <TabsList>
          <TabsTrigger value="global">
            <SettingsIcon className="h-4 w-4 mr-2" />
            Global
          </TabsTrigger>
          <TabsTrigger value="genicam">
            <Network className="h-4 w-4 mr-2" />
            GenICam
          </TabsTrigger>
          <TabsTrigger value="apriltag">
            <Tag className="h-4 w-4 mr-2" />
            AprilTag Fields
          </TabsTrigger>
          <TabsTrigger value="system">
            <HardDrive className="h-4 w-4 mr-2" />
            System
          </TabsTrigger>
        </TabsList>

        {/* Global Settings */}
        <TabsContent value="global" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Global Settings</CardTitle>
              <CardDescription>
                Configure team number, hostname, and network settings
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="team-number">Team Number</Label>
                <Input
                  id="team-number"
                  type="number"
                  value={teamNumber}
                  onChange={(e) => setTeamNumber(e.target.value)}
                  placeholder="Enter team number"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="hostname">Hostname</Label>
                <Input
                  id="hostname"
                  value={hostname}
                  onChange={(e) => setHostname(e.target.value)}
                  placeholder="arcsight-pi"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="ip-mode">IP Assignment Mode</Label>
                <Select value={ipMode} onValueChange={(v) => setIpMode(v as 'dhcp' | 'static')}>
                  <SelectTrigger id="ip-mode">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="dhcp">DHCP</SelectItem>
                    <SelectItem value="static">Static IP</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <Button onClick={handleSaveGlobal} disabled={isLoading}>
                {isLoading ? 'Saving...' : 'Save Global Settings'}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* GenICam Settings */}
        <TabsContent value="genicam" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>GenICam Settings</CardTitle>
              <CardDescription>
                Configure GenICam Transport Layer Interface (CTI) file path
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="cti-path">CTI File Path</Label>
                <Input
                  id="cti-path"
                  value={genicamPath}
                  onChange={(e) => setGenicamPath(e.target.value)}
                  placeholder="/path/to/producer.cti"
                />
                <p className="text-xs text-muted">
                  Path to the GenICam producer CTI file for industrial cameras
                </p>
              </div>

              <div className="flex gap-2">
                <Button onClick={handleSaveGenICam} disabled={isLoading}>
                  {isLoading ? 'Saving...' : 'Save Path'}
                </Button>
                <Button variant="outline" onClick={handleClearGenICam} disabled={isLoading}>
                  Clear Path
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* AprilTag Fields */}
        <TabsContent value="apriltag" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>AprilTag Field Layouts</CardTitle>
              <CardDescription>
                Manage FRC field layouts for AprilTag pose estimation
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="field-select">Active Field Layout</Label>
                {fieldOptions.length > 0 ? (
                  <Select value={selectedField} onValueChange={handleFieldChange}>
                    <SelectTrigger id="field-select">
                      <SelectValue placeholder="Select field layout" />
                    </SelectTrigger>
                    <SelectContent>
                      {fieldOptions.map((field) => (
                        <SelectItem key={field.value} value={field.value}>
                          {field.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                ) : (
                  <p className="text-sm text-muted">
                    No field layouts available. Upload a custom layout to begin.
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label>Upload Custom Field</Label>
                <Input type="file" accept=".json" />
                <p className="text-xs text-muted">
                  Upload a JSON file with custom AprilTag field layout
                </p>
              </div>

              <Button disabled={isLoading}>
                Upload Field Layout
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* System Controls */}
        <TabsContent value="system" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>System Controls</CardTitle>
              <CardDescription>
                Manage application lifecycle and database
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Button variant="outline" onClick={() => setConfirmAction('restart')}>
                  Restart Application
                </Button>
                <Button variant="outline" onClick={() => setConfirmAction('reboot')}>
                  Reboot Device
                </Button>
                <Button variant="outline" onClick={handleExportDatabase}>
                  Export Database
                </Button>
                <Button variant="outline">
                  Import Database
                </Button>
              </div>

              <div className="pt-4 border-t">
                <Button
                  variant="destructive"
                  onClick={() => setConfirmAction('factory-reset')}
                  className="w-full"
                >
                  Factory Reset
                </Button>
                <p className="text-xs text-muted mt-2 text-center">
                  Warning: This will erase all cameras, pipelines, and settings
                </p>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Confirmation Dialog */}
      <Dialog open={confirmAction !== null} onOpenChange={() => setConfirmAction(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-[var(--color-warning)]">
              <AlertTriangle className="h-5 w-5" />
              Confirm Action
            </DialogTitle>
            <DialogDescription>
              {confirmAction === 'restart' && 'Are you sure you want to restart the application? This will temporarily interrupt all camera feeds and pipelines.'}
              {confirmAction === 'reboot' && 'Are you sure you want to reboot the device? All processes will be stopped.'}
              {confirmAction === 'factory-reset' && 'Are you sure you want to reset all settings to factory defaults? This will erase all cameras, pipelines, and configuration. This action cannot be undone.'}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmAction(null)}>
              Cancel
            </Button>
            <Button
              variant={confirmAction === 'factory-reset' ? 'destructive' : 'default'}
              onClick={() => confirmAction && handleSystemAction(confirmAction)}
            >
              Confirm
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
