"""
Django management command to start the autonomous agent controller
"""

import asyncio
import logging
import signal
import sys
from django.core.management.base import BaseCommand
from apps.agents.controller import AsyncAutonomousController

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Start the autonomous agent controller for processing consultations'

    def add_arguments(self, parser):
        parser.add_argument(
            '--interval',
            type=int,
            default=2,
            help='Polling interval in seconds (default: 2)'
        )

    def handle(self, *args, **options):
        interval = options['interval']

        
        self.stdout.write(self.style.SUCCESS(' DocAssistant Autonomous Controller'))
        
        self.stdout.write(f'Polling interval: {interval}s')
        self.stdout.write(f'Press Ctrl+C to stop\n')

        controller = AsyncAutonomousController()

        async def main():
            # Start the controller background loop
            controller.start()

            # Event to signal shutdown
            stop_event = asyncio.Event()

            # Signal handlers for graceful shutdown
            def _signal_handler():
                self.stdout.write(self.style.WARNING('\n\n Shutting down controller...'))
                stop_event.set()

            # Register signals (works on Windows & Linux)
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, _signal_handler)
                except NotImplementedError:
                    # fallback for Windows
                    signal.signal(sig, lambda s, f: _signal_handler())

            self.stdout.write(self.style.SUCCESS(' Controller started. Monitoring consultations...\n'))

            # Keep main loop alive until stop_event is set
            await stop_event.wait()
            await controller.stop()
            self.stdout.write(self.style.SUCCESS(' Controller stopped.'))

        # Run the async main() safely
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\n\n Controller stopped by user'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n\n Controller error: {e}'))
            logger.error(f'Controller error: {e}', exc_info=True)
            sys.exit(1)